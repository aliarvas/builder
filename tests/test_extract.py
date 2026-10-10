"""Offline tests for spec extraction (T-006). No network: a fake client returns recorded replies."""

from __future__ import annotations

import copy
import datetime
import io
import json
import os
import re
import socket
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from builder import build
from builder.extract import (
    FRAMEWORK_NAMES,
    MAX_REPAIR_ROUNDS,
    ExtractionError,
    _Checker,
    brief_dates,
    brief_items,
    check_spec_data,
    extract_spec,
    resolve_path,
)
from builder.llm import AnthropicClient, LLMError
from builder.spec import CLOSE_STATE_NAMES
from builder.tools_from_openapi import tool_contract
from tests.extract_helpers import FakeClient, as_text, groups_from_spec
from tools.compare_spec import compare_specs

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "build-the-builder-v2"
OPENAPI = json.loads((KIT / "tools/openapi.json").read_text(encoding="utf-8"))
BRIEF_A = [("brief-a.md", (KIT / "briefs/brief-a.md").read_text(encoding="utf-8"))]
BRIEF_AB = BRIEF_A + [("brief-b.md", (KIT / "briefs/brief-b.md").read_text(encoding="utf-8"))]
FIXTURE_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
FIXTURE_B = json.loads((ROOT / "tests/fixtures/spec-brief-b.json").read_text(encoding="utf-8"))
RECORDED_A = json.loads((ROOT / "tests/fixtures/extract/brief-a-replies.json").read_text(encoding="utf-8"))


def all_covered(documents):
    return {"items": [{"id": number, "status": "covered", "paths": ["global_rules[0]"]}
                      for number, _ in brief_items(documents)]}


def replies_for(groups, documents, **overrides):
    replies = {name: [as_text(value)] for name, value in groups.items()}
    replies["coverage"] = [as_text(all_covered(documents))]
    replies.update(overrides)
    return replies


def run(groups=RECORDED_A, documents=BRIEF_A, **overrides):
    logs = []
    client = FakeClient(replies_for(groups, documents, **overrides))
    result = extract_spec(documents, OPENAPI, client, log=lambda key, value: logs.append((key, str(value))))
    return result, client, logs


class ExtractionPipelineTests(unittest.TestCase):
    def test_recorded_replies_produce_the_reference_spec(self):
        result, client, _ = run()
        self.assertEqual([], compare_specs(result.spec_data, FIXTURE_A))
        self.assertEqual(FRAMEWORK_NAMES["who_answered_variable"], result.spec.opening.data["who_answered_variable"])
        self.assertIn("opening.max_unclear_asks", result.spec_data["provenance"])
        self.assertEqual(
            ["coverage", "extract:flow", "extract:offer", "extract:opening_identity", "extract:outcomes"],
            sorted(client.purposes()),
        )

    def test_multi_document_round_trip(self):
        result, _, _ = run(groups_from_spec(FIXTURE_B), BRIEF_AB)
        self.assertEqual([], compare_specs(result.spec_data, FIXTURE_B))

    def test_group_calls_run_in_parallel(self):
        # Each first call waits for the other three: a sequential pipeline would break the barrier.
        barrier = threading.Barrier(4, timeout=5)
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A), barrier=barrier)
        extract_spec(BRIEF_A, OPENAPI, client)
        self.assertFalse(barrier.broken)

    def test_shared_context_is_cached_and_task_differs(self):
        _, client, _ = run()
        first = {purpose: messages[0]["content"] for purpose, messages in client.calls}
        contexts = {blocks[0]["text"] for blocks in first.values()}
        self.assertEqual(1, len(contexts))
        self.assertTrue(all(blocks[0].get("cache_control") for blocks in first.values()))
        self.assertEqual(len(first), len({blocks[1]["text"] for blocks in first.values()}))
        self.assertIn("Document 1 of 1: brief-a.md", contexts.pop())

    def test_broken_section_is_repaired_with_only_its_errors(self):
        broken = copy.deepcopy(RECORDED_A["outcomes"])
        for row in broken["outcomes"]:
            row["states"] = [state for state in row["states"] if state != "identity_failed"]
        broken["special_paths"][2]["tool_args"]["queue"] = "nobody"
        result, client, logs = run(outcomes=[as_text(broken), as_text(RECORDED_A["outcomes"])])
        self.assertEqual([], compare_specs(result.spec_data, FIXTURE_A))
        repairs = [(purpose, messages) for purpose, messages in client.calls if purpose.startswith("repair")]
        self.assertEqual(["repair1:outcomes"], [purpose for purpose, _ in repairs])
        repair_message = repairs[0][1][-1]["content"]
        self.assertIsInstance(repair_message, str)
        self.assertIn("identity_failed", repair_message)
        self.assertNotIn("Freya Bank is fictional", repair_message)
        # The repair continues the same conversation: the first reply is in context.
        self.assertEqual("assistant", repairs[0][1][-2]["role"])
        self.assertIn(("extract_round", "round=0 failing_groups=outcomes errors=1"), logs)

    def test_contract_error_found_after_merge_is_sent_to_the_owning_group(self):
        broken = copy.deepcopy(RECORDED_A["outcomes"])
        broken["special_paths"][2]["tool_args"]["queue"] = "nobody"
        _, client, _ = run(outcomes=[as_text(broken), as_text(RECORDED_A["outcomes"])])
        repair = next(messages for purpose, messages in client.calls if purpose == "repair1:outcomes")
        self.assertIn("special_paths[2].tool_args.queue", repair[-1]["content"])

    def test_invalid_json_is_repaired(self):
        result, client, _ = run(flow=["Here is the JSON you asked for.", as_text(RECORDED_A["flow"])])
        self.assertIn("repair1:flow", client.purposes())
        self.assertIn("not one valid JSON object", next(
            messages[-1]["content"] for purpose, messages in client.calls if purpose == "repair1:flow"
        ))
        self.assertEqual([], compare_specs(result.spec_data, FIXTURE_A))

    def test_routed_close_must_use_a_table_row(self):
        # The pair is written in the documents, but the outcomes call left its row out.
        outcomes = copy.deepcopy(RECORDED_A["outcomes"])
        outcomes["outcomes"] = [row for row in outcomes["outcomes"] if (row["outcome"], row["reason"]) != ("not_verified", "declined")]
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A, outcomes=[as_text(outcomes)]))
        with self.assertRaises(ExtractionError):
            extract_spec(BRIEF_A, OPENAPI, client)
        repair = next(messages for purpose, messages in client.calls if purpose == "repair1:opening_identity")
        self.assertIn("not a closing-table row", repair[-1]["content"])

    def test_routed_close_with_a_pair_from_two_table_rows_is_repaired(self):
        broken = copy.deepcopy(RECORDED_A["opening_identity"])
        end = next(entry for entry in broken["opening"]["answers"] if entry["route"] == "end")
        # Both words are in the closing table, in neighbouring rows, never in one row.
        end["outcome"], end["reason"] = "not_reached", "failed"
        _, client, _ = run(opening_identity=[as_text(broken), as_text(RECORDED_A["opening_identity"])])
        repair = next(messages for purpose, messages in client.calls if purpose == "repair1:opening_identity")
        self.assertIn("pair not_reached/failed not found together", repair[-1]["content"])

    def test_failure_after_repair_rounds_lists_every_problem(self):
        broken = copy.deepcopy(RECORDED_A["offer"])
        broken["offer"]["holidays"] = ["2026-13-40"]
        broken["offer"]["latest"][0]["when"][0]["field"] = "no_such_field"
        logs = []
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A, offer=[as_text(broken)]))
        with self.assertRaises(ExtractionError) as caught:
            extract_spec(BRIEF_A, OPENAPI, client, log=lambda key, value: logs.append((key, str(value))))
        self.assertEqual(MAX_REPAIR_ROUNDS, sum(1 for p in client.purposes() if p.startswith("repair")))
        self.assertNotIn("coverage", client.purposes())
        self.assertTrue(caught.exception.problems)
        self.assertTrue(all(problem.startswith("[offer]") for problem in caught.exception.problems))
        self.assertIn("2 repair rounds", str(caught.exception))
        self.assertTrue(any(key == "extract_error" for key, _ in logs))

    def test_coverage_reask_adds_valid_rules_and_drops_breaking_ones(self):
        items = brief_items(BRIEF_A)
        coverage = all_covered(BRIEF_A)
        coverage["items"][0]["status"] = "missing"
        coverage["items"][1] = {"id": items[1][0], "status": "covered", "paths": ["no_such.path[3]"]}
        coverage["items"][2]["status"] = "not_relevant"
        coverage["items"].pop()  # an id the model forgot counts as missing
        followup = {"additions": [
            {"items": [items[0][0]], "target": "global_rules", "value": {"text": "A rule.", "source": items[0][1]}},
            {"items": [items[1][0]], "target": "special_paths", "value": {"id": "bad"}},
        ], "not_relevant": [{"item": items[-1][0], "why": "background"}]}
        result, client, logs = run(coverage=[as_text(coverage)], coverage_followup=[as_text(followup)])
        self.assertIn("coverage_followup", client.purposes())
        self.assertEqual("A rule.", result.spec.global_rules[-1].text)
        self.assertEqual([f"{items[1][0]}: {items[1][1]}"], result.unmapped)
        self.assertEqual(result.unmapped, result.spec_data["coverage"]["unmapped"])
        keys = [key for key, _ in logs]
        self.assertIn("coverage_added", keys)
        self.assertIn("coverage_rejected", keys)
        self.assertIn("coverage_unmapped", keys)

    def test_coverage_failure_does_not_block_a_valid_spec_and_is_traced_by_kind(self):
        total = len(brief_items(BRIEF_A))
        for reply, kind in (("not json", "invalid_json"), ('{"answer": 1}', "bad_shape")):
            result, _, logs = run(coverage=[reply])
            self.assertEqual(total, len(result.unmapped))
            self.assertEqual("not run", result.spec_data["coverage"]["check"])
            self.assertIn(("coverage_error", f"purpose=coverage kind={kind}"), [
                (key, value.split(" detail=")[0]) for key, value in logs
            ])
            self.assertEqual(total, sum(1 for key, _ in logs if key == "coverage_unmapped"))

    def test_coverage_model_call_failure_is_its_own_kind(self):
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A))
        original = client.complete

        def complete(system, messages, purpose):
            if purpose == "coverage":
                raise LLMError("model call 'coverage' failed: HTTP 529: overloaded")
            return original(system, messages, purpose)

        client.complete = complete
        logs = []
        result = extract_spec(BRIEF_A, OPENAPI, client, log=lambda key, value: logs.append((key, str(value))))
        self.assertTrue(result.unmapped)
        self.assertTrue(any(key == "coverage_error" and "kind=model_call" in value for key, value in logs))


class ValidationRuleTests(unittest.TestCase):
    def check(self, spec):
        brief = "\n\n".join(text for _, text in BRIEF_A)
        checker = _Checker(brief, tool_contract(OPENAPI), set())
        check_spec_data(spec, checker)
        return [f"{path}: {message}" for path, message in checker.errors]

    def test_reference_spec_has_no_errors(self):
        self.assertEqual([], self.check(FIXTURE_A))

    def test_contract_and_evidence_errors(self):
        spec = copy.deepcopy(FIXTURE_A)
        spec["identity"]["questions"][0]["field"] = "mother_maiden_name"
        spec["identity"]["verified_field"] = "wrong_answers_left"
        spec["account"]["product_id_field"] = "id"
        spec["confirmation"]["promise_date_field"] = "when"
        spec["outcomes"][4]["reason"] = "too_expensive"
        spec["outcomes"][5]["outcome"] = "escalated"
        spec["special_paths"][2]["tool_args"] = {"queue": "nobody", "priority": "high"}
        spec["special_paths"][0]["tool"] = "create_promise"
        spec["offer"]["min_amount"][0]["when"][0]["in"] = ["mortgage"]
        spec["offer"]["today_variable"] = "time_of_call"
        errors = "\n".join(self.check(spec))
        for expected in (
            "identity.questions", "identity.verified_field", "account.product_id_field",
            "confirmation.promise_date_field", "outcomes[4]: pair no_promise/too_expensive", "outcomes[5].outcome",
            "special_paths[2].tool_args.queue", "special_paths[2].tool_args.priority", "special_paths[0].tool",
            "offer.min_amount[0].when[0]", "offer.today_variable",
        ):
            self.assertIn(expected, errors)

    def test_outcome_reason_pairs_must_be_written_together(self):
        spec = copy.deepcopy(FIXTURE_A)
        spec["outcomes"][4]["outcome"], spec["outcomes"][4]["reason"] = "not_reached", "refused"
        spec["special_paths"][1]["outcome"], spec["special_paths"][1]["reason"] = "transferred", "dispute"
        errors = "\n".join(self.check(spec))
        self.assertIn("outcomes[4]: pair not_reached/refused not found together", errors)
        self.assertIn("special_paths[1]: pair transferred/dispute not found together", errors)
        # An outcome without a reason is enough on its own; the reference spec stays clean.
        self.assertNotIn("outcomes[0]", errors)

    def check_text(self, brief, spec):
        checker = _Checker(brief, tool_contract(OPENAPI), set())
        check_spec_data(spec, checker)
        return "\n".join(f"{path}: {message}" for path, message in checker.errors)

    def test_holidays_and_day_counts_need_evidence_in_any_date_form(self):
        brief = BRIEF_A[0][1]
        spec = copy.deepcopy(FIXTURE_A)
        spec["offer"]["holidays"].append("2026-12-24")
        spec["offer"]["latest"][0]["days"] = 13
        errors = self.check_text(brief, spec)
        self.assertIn("offer.holidays[5]: 2026-12-24 is not a date written", errors)
        self.assertIn("offer.latest[0].days: 13 does not appear", errors)
        self.assertNotIn("offer.holidays[0]", errors)
        self.assertNotIn("offer.earliest", errors)  # 0 days: "today"

        # The same dates and counts written in words: accepted after normalization.
        words = re.sub(r"2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01",
                       "26 October 2026, Nov 11, November 26th, 2026, 25/12/2026 and 1st January 2027", brief)
        words = words.replace("the 12th business day", "the twelfth business day").replace("the 7th", "the seventh")
        self.assertNotEqual(brief, words)
        self.assertEqual("", self.check_text(words, FIXTURE_A))
        self.assertIn("2026-11-26 is not a date written", self.check_text(words.replace("November 26th, 2026", ""), FIXTURE_A))

    def test_brief_dates_forms(self):
        full, month_days = brief_dates("On 3 March 2027, March 4, 2027, 2027-03-05, 06.03.2027, 2 Feb and 31 June.")
        for day in ("2027-03-03", "2027-03-04", "2027-03-05", "2027-03-06", "2027-06-03"):
            self.assertIn(datetime.date.fromisoformat(day), full)
        self.assertEqual({(2, 2)}, month_days)  # "31 June" is not a date

    def test_rule_citing_overridden_text_is_an_error(self):
        spec = copy.deepcopy(FIXTURE_A)
        spec["overrides"] = [{"newer": "Ask once more.", "older": "Ask \"Am I speaking with {title} {last_name}?\".",
                              "effect": "test"}]
        spec["opening"]["rules"][0]["source"] = "Ask \"Am I speaking with {title} {last_name}?\"."
        self.assertTrue(any("overrides" in error for error in self.check(spec)))

    def test_brief_items_split_sentences_and_rows_and_skip_headings(self):
        items = [text for _, text in brief_items([("x.md", "# Title\n\nOne rule. Two rule.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n- item")])]
        self.assertEqual(["One rule.", "Two rule.", "A | B", "1 | 2", "- item"], items)

    def test_resolve_path(self):
        self.assertTrue(resolve_path(FIXTURE_A, "special_paths[2].tool_args.queue"))
        self.assertTrue(resolve_path(FIXTURE_A, "$.offer.holidays"))
        self.assertFalse(resolve_path(FIXTURE_A, "special_paths[9]"))
        self.assertFalse(resolve_path(FIXTURE_A, "offer..holidays x"))


class ExtractionPromptTests(unittest.TestCase):
    def test_extraction_prompts_carry_no_brief_values(self):
        import re

        from builder import prompts

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        # Codes from the practice fixtures and tool enums (skeleton step and state names excluded),
        # plus single-word outcome, reason and queue codes and practice-brief examples.
        skeleton = {"third_party", "confirm_record", *CLOSE_STATE_NAMES}
        codes = {
            value for value in [*strings(FIXTURE_A), *strings(FIXTURE_B), *strings(OPENAPI)]
            if re.fullmatch(r"[a-z]+(_[a-z0-9]+)+", value) and value not in skeleton
        } | {"paid", "transferred", "refused", "hardship", "dispute", "restructuring", "general", "support",
             "declined", "deceased", "Freya", "robot", "scam"}
        names = [name for name in dir(prompts) if name.startswith(("EXTRACT", "COVERAGE", "CLOSE_STATE"))]
        self.assertGreaterEqual(len(names), 10)
        found = {
            (name, code) for name in names for code in codes
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(code) + r"(?![A-Za-z0-9_])", getattr(prompts, name).text)
        }
        self.assertEqual(set(), found)
        for name in names:
            self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}", getattr(prompts, name).text), name)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _ok_body(text="{}"):
    return json.dumps({
        "model": "claude-test", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
    }).encode()


class AnthropicClientTests(unittest.TestCase):
    KEY = "sk-ant-test-secret-123"

    def test_missing_key_fails_clearly(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(LLMError) as caught:
            AnthropicClient()
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))

    def test_request_shape_retry_and_logging_without_key(self):
        sent, logged = [], []

        def opener(request, timeout):
            sent.append(request)
            if len(sent) == 1:
                raise urllib.error.URLError(socket.timeout("slow"))
            return _Response(_ok_body("hello"))

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}), patch("builder.llm.time.sleep"):
            client = AnthropicClient(opener=opener, log=lambda purpose, result: logged.append((purpose, result)))
            result = client.complete("system", [{"role": "user", "content": "hi"}], "extract:test")
        self.assertEqual(2, len(sent))
        payload = json.loads(sent[-1].data)
        self.assertNotIn("temperature", payload)  # the pinned model rejects it
        self.assertEqual("claude-sonnet-5-5", payload["model"])
        self.assertEqual(self.KEY, sent[-1].get_header("X-api-key"))
        self.assertEqual(("hello", 10, 5, 3), (result.text, result.input_tokens, result.output_tokens, result.cache_read_tokens))
        self.assertEqual("extract:test", logged[0][0])
        self.assertNotIn(self.KEY, repr(logged))

    def test_second_transport_failure_raises_without_key(self):
        def opener(request, timeout):
            raise urllib.error.URLError(f"refused {self.KEY}")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}), patch("builder.llm.time.sleep"), \
                self.assertRaises(LLMError) as caught:
            AnthropicClient(opener=opener).complete("s", [], "coverage")
        self.assertNotIn(self.KEY, str(caught.exception))

    def test_temperature_rejection_is_resent_without_it(self):
        sent = []

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            if len(sent) == 1:
                raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b'{"error": "temperature is not supported"}'))
            return _Response(_ok_body())

        notes = []
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}):
            client = AnthropicClient(opener=opener, temperature=0, note=notes.append)
            client.complete("s", [], "x")
        self.assertEqual(0, sent[0]["temperature"])
        self.assertNotIn("temperature", sent[1])
        self.assertEqual(1, len(notes))
        self.assertIn("temperature=not sent", client.settings())

    def test_parallel_temperature_rejections_are_all_resent(self):
        # All four parallel requests carry a temperature and fail together. A request must be
        # resent because its own payload had one, even after another thread changed the setting.
        barrier = threading.Barrier(4, timeout=5)
        sent, lock = [], threading.Lock()

        def opener(request, timeout):
            payload = json.loads(request.data)
            with lock:
                sent.append(payload)
            if "temperature" in payload:
                barrier.wait()
                raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(
                    b'{"error": "temperature is deprecated for this model"}'))
            return _Response(_ok_body("{}"))

        notes = []
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}):
            client = AnthropicClient(opener=opener, temperature=0, note=notes.append)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda n: client.complete("s", [], f"extract:{n}"), range(4)))
        self.assertEqual(4, len(results))
        self.assertEqual(8, len(sent))
        self.assertEqual(4, sum(1 for payload in sent if "temperature" in payload))
        self.assertEqual(1, len(notes))
        self.assertIsNone(client.temperature)

    def test_temperature_rejection_keeps_the_transport_retry(self):
        sent = []

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            if len(sent) == 1:
                raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b'{"error": "temperature is deprecated"}'))
            if len(sent) == 2:
                raise urllib.error.URLError("reset")
            return _Response(_ok_body())

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}), patch("builder.llm.time.sleep"):
            AnthropicClient(opener=opener, temperature=0).complete("s", [], "x")
        self.assertEqual(3, len(sent))

    def test_output_limit_is_an_error(self):
        body = json.loads(_ok_body())
        body["stop_reason"] = "max_tokens"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}), self.assertRaises(LLMError):
            AnthropicClient(opener=lambda request, timeout: _Response(json.dumps(body).encode())).complete("s", [], "x")


class BuildIntegrationTests(unittest.TestCase):
    KEY = "sk-ant-build-secret-456"

    def run_build(self, replies, slot="extracted"):
        def fake_client(log=None, note=None):
            return FakeClient(replies, log=log)

        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": self.KEY}), \
                        patch("builder.build.AnthropicClient", side_effect=fake_client), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    code = build.main([str(KIT / "briefs/brief-a.md"), str(KIT / "tools/openapi.json"),
                                       "--print", "--slot", slot])
                traces = {path.name: path.read_text(encoding="utf-8") for path in Path("traces").iterdir()}
                return code, stdout.getvalue(), stderr.getvalue(), traces
            finally:
                os.chdir(previous)

    def test_build_without_spec_extracts_writes_spec_and_traces_calls(self):
        code, stdout, _, traces = self.run_build(replies_for(RECORDED_A, BRIEF_A))
        self.assertEqual(0, code)
        self.assertEqual("opening", json.loads(stdout)["initial_node"])
        spec = json.loads(traces["extracted.spec.json"])
        self.assertEqual([], compare_specs(spec, FIXTURE_A))
        trace = traces["extracted.print.log"]
        self.assertEqual(5, trace.count("model_call: model=fake-model"))
        self.assertIn("purpose=extract:outcomes input_tokens=1000 output_tokens=200", trace)
        self.assertIn("model_calls: 5 input_tokens=5000 output_tokens=1000", trace)
        self.assertIn("renderer: multi-step spec_version=1", trace)
        self.assertIn("model_settings: model=fake-model temperature=not sent", trace)
        self.assertIn("coverage: items=", trace)
        self.assertNotIn(self.KEY, "".join(traces.values()))
        self.assertNotIn("not mapped", stdout)

    def test_unmapped_items_give_a_one_line_warning_at_the_end(self):
        coverage = all_covered(BRIEF_A)
        coverage["items"][0]["status"] = "missing"
        followup = {"additions": [], "not_relevant": []}
        replies = replies_for(RECORDED_A, BRIEF_A, coverage=[as_text(coverage)], coverage_followup=[as_text(followup)])
        code, stdout, stderr, traces = self.run_build(replies, "gaps")
        self.assertEqual(0, code)
        json.loads(stdout)  # --print stdout stays pure JSON
        last = stderr.strip().splitlines()[-1]
        self.assertEqual("warning: 1 brief item(s) not mapped to the spec; see coverage_unmapped in traces/gaps.print.log", last)
        self.assertIn("coverage_unmapped: 1: ", traces["gaps.print.log"])

    def test_build_stops_with_listed_fields_when_extraction_fails(self):
        broken = copy.deepcopy(RECORDED_A["offer"])
        broken["offer"]["latest"][0]["when"][0]["field"] = "no_such_field"
        code, stdout, stderr, traces = self.run_build(replies_for(RECORDED_A, BRIEF_A, offer=[as_text(broken)]), "bad")
        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertIn("spec extraction failed", stderr)
        trace = traces["bad.failed.log"]
        self.assertIn("extract_error: [offer] offer.latest[0].when[0].field", trace)
        self.assertIn("bad.spec.failed.json", trace)
        self.assertIn("bad.spec.failed.json", traces)
        self.assertNotIn("bad.spec.json", traces)


if __name__ == "__main__":
    unittest.main()
