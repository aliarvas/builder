"""T-009: prompt budget guard and rule placement (offline)."""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from builder.spec import SpecError, parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import (
    PROMPT_HARD_LIMIT_TOKENS,
    PROMPT_TARGET_TOKENS,
    build_spec_workflow,
    SANDBOX_PAYLOAD_LIMIT,
    VARIABLE_RESERVE_BYTES,
    enforcement_available,
    workflow_code_payloads,
    workflow_prompt_estimates,
)

ROOT = Path(__file__).resolve().parents[1]
TOOLS = tools_from_openapi(json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")))
FIXTURE_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
# Live A+B extraction (traces/f040-b.spec.json), and the same spec with enforced_by tags as
# the T-009 extraction prompt asks for them (added by hand; see tasks/T-009-report.md).
AB = json.loads((ROOT / "tests/fixtures/extract/brief-ab-extracted.json").read_text(encoding="utf-8"))
AB_TAGGED = json.loads((ROOT / "tests/fixtures/extract/brief-ab-extracted-tagged.json").read_text(encoding="utf-8"))


def all_rule_keys(data):
    keys = [f"global_rules[{i}]" for i in range(len(data["global_rules"]))]
    for section in ("opening", "third_party", "identity", "account", "negotiation", "confirmation", "offer", "closing"):
        keys += [f"{section}.rules[{i}]" for i in range(len(data[section]["rules"]))]
    return keys


def render(data, **kwargs):
    warnings, placements = [], []
    workflow = build_spec_workflow(parse_spec(copy.deepcopy(data)), TOOLS, warnings, placements, **kwargs)
    return workflow, warnings, placements


class PromptBudgetTests(unittest.TestCase):
    def test_tagged_extraction_fits_and_every_rule_is_placed_once(self):
        workflow, warnings, placements = render(AB_TAGGED)
        estimates = workflow_prompt_estimates(workflow)
        # With runtime text counted (F-053 fix), negotiate and its two waiting copies stay over the
        # target even with honest tags; the other steps fit.
        over = {key for key, value in estimates.items() if value > PROMPT_TARGET_TOKENS}
        self.assertEqual({"negotiate", "offer_say", "revise_ask"}, over)
        self.assertTrue(any(warning.startswith("negotiate: prompt") for warning in warnings))
        rule_lines = [line for line in placements if not line.startswith("budget")]
        placed = [line.split(" -> ")[0] for line in rule_lines]
        self.assertEqual(sorted(all_rule_keys(AB_TAGGED)), sorted(placed))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertIn("budget stages: code-enforced rules left out; duplicate wording removed", placements)
        # Tagged closing rules start in the global prompt and leave it only under budget pressure.
        line = next(line for line in placements if line.startswith("budget negotiate: "))
        before, after = map(int, re.findall(r"~(\d+)", line)[:2])
        self.assertGreater(before - after, 250)  # the stages remove the code-enforced and duplicate rules

    def test_left_out_rules_are_only_tagged_or_duplicates(self):
        workflow, _, placements = render(AB_TAGGED)
        prompts = workflow["system_prompt"] + "".join(node.get("task_message", "") for node in workflow["nodes"].values())
        for line in placements:
            if " -> not in a prompt (" not in line:
                continue
            reason = line.split(" -> not in a prompt (")[1]
            self.assertTrue(reason.startswith(("code: ", "duplicate of ")), line)
            if reason.startswith("duplicate of "):
                original = reason.split()[2]
                self.assertTrue(any(l.startswith(original + " -> ") and " -> not in a prompt" not in l
                                    for l in placements), line)
        # A tagged rule's text is really gone from the prompts; an untagged closing rule is not.
        self.assertNotIn("Accept any amount from the floor up to the full past-due amount", prompts)
        self.assertIn("On any transfer add no notes", workflow["system_prompt"])

    def test_untagged_extraction_ships_with_a_clear_warning(self):
        # CTO decision (T-009b): over the hard limit the step ships with every rule.
        workflow, warnings, placements = render(AB)
        self.assertGreater(workflow_prompt_estimates(workflow)["negotiate"], PROMPT_HARD_LIMIT_TOKENS)
        exceeded = [line for line in placements if line.startswith("budget_exceeded_but_shipped negotiate: ~")]
        self.assertEqual(1, len(exceeded))
        self.assertTrue(exceeded[0].endswith("tokens > limit 1500 after all budget stages; shipped with every rule"))
        self.assertTrue(any("over the hard limit 1500; shipped anyway, no rule cut" in w for w in warnings))
        rule_lines = [l for l in placements if not l.startswith("budget")]
        self.assertEqual(sorted(all_rule_keys(AB)), sorted(l.split(" -> ")[0] for l in rule_lines))
        # Untagged: only a rule about a tool that a code loop calls leaves for code (T-009d).
        to_code = [l for l in rule_lines if " -> not in a prompt (code: " in l]
        self.assertTrue(all("is called by code (" in l for l in to_code), to_code)

    def test_many_rules_trigger_the_guard_and_ship_with_a_warning(self):
        data = copy.deepcopy(FIXTURE_A)
        data["negotiation"]["rules"] += [
            {"text": f"Synthetic policy rule number {i} with enough words to take real room in the prompt.", "source": "x"}
            for i in range(60)
        ]
        workflow, _, placements = render(data)
        self.assertTrue(any(line.startswith("budget_exceeded_but_shipped negotiate:") for line in placements))
        self.assertIn("Synthetic policy rule number 59", workflow["nodes"]["negotiate"]["task_message"])
        _, warnings, placements = render(data, hard_limit_tokens=10_000)
        self.assertTrue(any("over the target" in warning for warning in warnings))
        self.assertTrue(any(line.startswith("budget negotiate:") for line in placements))

    def test_small_spec_is_unchanged(self):
        workflow, warnings, placements = render(FIXTURE_A)
        self.assertFalse(any(line.startswith("budget stages") for line in placements))
        self.assertTrue(all(" -> step " in line or " -> global prompt " in line
                            for line in placements if not line.startswith("budget")))
        self.assertFalse(any("over the target" in warning for warning in warnings))

    def test_duplicates_are_whole_sentences_only(self):
        data = copy.deepcopy(FIXTURE_A)
        data["negotiation"]["rules"] = [
            {"text": "Offer the floor.", "source": "x"},
            {"text": "Do not offer the floor. Stop.", "source": "x"},
            {"text": "Ask once. Then stop.", "source": "x"},
            {"text": "ask once!", "source": "x"},
        ]
        _, _, placements = render(data, target_tokens=1)
        line = lambda key: next(l for l in placements if l.startswith(key + " -> "))
        self.assertIn(" -> step negotiate", line("negotiation.rules[0]"))
        self.assertIn("duplicate of negotiation.rules[2]", line("negotiation.rules[3]"))

    def test_rule_shared_by_two_steps_moves_to_the_global_prompt(self):
        data = copy.deepcopy(FIXTURE_A)
        shared = {"text": "Speak slowly and clearly to the customer at every point.", "source": "x"}
        data["identity"]["rules"].append(dict(shared))
        data["confirmation"]["rules"].append(dict(shared))
        workflow, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
        self.assertEqual(1, workflow["system_prompt"].count("Speak slowly and clearly"))
        self.assertNotIn("Speak slowly and clearly", workflow["nodes"]["identity"]["task_message"])
        self.assertIn("budget stages: shared rules moved to the global prompt", placements)
        self.assertTrue(any(l.startswith("identity.rules[1] -> global prompt (moved: was in confirm_record, identity)")
                            for l in placements))
        self.assertTrue(any(l.startswith("confirmation.rules[2] -> not in a prompt (duplicate of identity.rules[1]")
                            for l in placements))

    def test_tag_without_its_data_keeps_the_rule(self):
        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["next_weekday"] = "ask"
        data["offer"]["rules"] = [{"text": "Next Friday means the Friday of next week.", "source": "x",
                                   "enforced_by": "weekday_reading"}]
        workflow, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
        self.assertIn("Next Friday means", workflow["nodes"]["negotiate"]["task_message"])
        self.assertTrue(any("tagged weekday_reading but this spec has no data" in line for line in placements))

    def test_enforcement_needs_the_spec_data(self):
        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["latest"] = []  # no latest date: a deadline rule is not enforced by code
        data["offer"]["rules"] = [{"text": "Never record a date after the deadline.", "source": "x",
                                   "enforced_by": "offer_dates"}]
        workflow, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
        self.assertIn("Never record a date after the deadline.", workflow["nodes"]["negotiate"]["task_message"])
        self.assertTrue(any("tagged offer_dates but this spec has no data" in line for line in placements))
        spec = parse_spec(copy.deepcopy(FIXTURE_A))
        for check in ("offer_dates", "business_days", "offer_amounts", "weekday_reading", "invalid_offer_limit",
                      "identity_attempts", "closing_outcome"):
            self.assertTrue(enforcement_available(spec, check), check)
        self.assertFalse(enforcement_available(spec, "magic"))

    def test_build_ships_over_budget_and_warns_at_the_end(self):
        import io
        import os
        import tempfile
        from contextlib import redirect_stderr, redirect_stdout

        from builder import build

        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = build.main([
                        str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                        str(ROOT / "build-the-builder-v2/tools/openapi.json"),
                        "--spec", str(ROOT / "tests/fixtures/extract/brief-ab-extracted.json"),
                        "--print", "--slot", "over",
                    ])
                trace = Path("traces/over.print.log").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)
        self.assertEqual(0, code)
        json.loads(stdout.getvalue())  # --print stdout stays the workflow JSON
        self.assertRegex(trace, r"budget_exceeded_but_shipped: negotiate: ~\d+ tokens > limit 1500")
        self.assertRegex(
            stderr.getvalue().strip().splitlines()[-1],
            r"^warning: prompt budget exceeded but shipped: negotiate: ~\d+ tokens > limit 1500 after all budget "
            r"stages; shipped with every rule; .*\(see traces/over.print.log\)$",
        )

    def test_unknown_enforcement_tag_is_a_spec_error(self):
        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["rules"] = [{"text": "x", "source": "x", "enforced_by": "magic"}]
        with self.assertRaises(SpecError):
            parse_spec(data)

    def test_tagged_closing_rule_follows_the_budget_policy(self):
        data = copy.deepcopy(FIXTURE_A)
        data["closing"]["rules"] = [
            {"text": "Call close_call exactly once, last.", "source": "x", "enforced_by": "closing_outcome"},
            {"text": "Add no notes on a transfer.", "source": "x"},
        ]
        # Within budget the tagged closing rule stays in the global prompt (T-009b, review finding 1).
        workflow, _, placements = render(data)
        self.assertIn("close_call exactly once, last", workflow["system_prompt"])
        self.assertIn("Add no notes on a transfer.", workflow["system_prompt"])
        self.assertTrue(any(l.startswith("closing.rules[0] -> global prompt (closing rule, no step prompt; code also "
                                         "enforces closing_outcome, kept: within budget)") for l in placements))
        # Under budget pressure it moves to code; the untagged one stays.
        workflow, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
        self.assertNotIn("close_call exactly once, last", workflow["system_prompt"])
        self.assertIn("Add no notes on a transfer.", workflow["system_prompt"])
        self.assertTrue(any(l.startswith("closing.rules[0] -> not in a prompt (code: closing_outcome)") for l in placements))


# Fresh A+B extraction (traces/ab-fresh.spec.json): no tags for the F-061/F-062 checks.
AB_FRESH = json.loads((ROOT / "tests/fixtures/extract/brief-ab-extracted-v2.json").read_text(encoding="utf-8"))


def place(placements, key):
    return next(line for line in placements if line.startswith(key + " -> "))


class BudgetT009dTests(unittest.TestCase):
    def test_fresh_ab_spec_shrinks_and_every_rule_is_placed_once(self):
        workflow, _, placements = render(AB_FRESH)
        estimates = workflow_prompt_estimates(workflow)
        # 1744 before T-009d; still over the limit (the review fix keeps every doubtful rule), so
        # the build ships with the budget warning.
        for key in ("negotiate", "offer_say", "revise_ask"):
            self.assertLess(estimates[key], 1700, key)
        rule_lines = [line for line in placements if not line.startswith("budget")]
        placed = [line.split(" -> ")[0] for line in rule_lines]
        self.assertEqual(sorted(all_rule_keys(AB_FRESH)), sorted(placed))
        # The four negotiation rules copied word for word in offer.rules are said once (AB-FRESH risk 2).
        task = workflow["nodes"]["negotiate"]["task_message"]
        for index in (7, 8, 17):
            text = AB_FRESH["negotiation"]["rules"][index]["text"]
            self.assertEqual(1, task.count(text), text)
        self.assertIn("(code: same wording as offer.rules[4] (offer_dates))", place(placements, "negotiation.rules[18]"))
        self.assertNotIn(AB_FRESH["negotiation"]["rules"][18]["text"], task)
        # A shorter copy inside a longer rule of the same step.
        self.assertIn("duplicate of offer.rules[5] (step negotiate; its wording contains this rule)",
                      place(placements, "negotiation.rules[19]"))
        # The scam rule is the path's own line in every step.
        self.assertIn("not in a prompt (special path scam_question", place(placements, "global_rules[1]"))
        # Review fixes 2 and 3: rules with a condition stay without a tag.
        self.assertIn("-> global prompt (its section)", place(placements, "global_rules[3]"))  # "before and after"
        self.assertIn("-> step negotiate", place(placements, "negotiation.rules[22]"))  # "without", "when no"

    def test_with_the_new_tags_the_counting_and_note_rules_go_to_code(self):
        # What the T-009d extraction prompt asks for, added by hand.
        data = copy.deepcopy(AB_FRESH)
        for index in (4, 5, 11):
            data["negotiation"]["rules"][index]["enforced_by"] = "persuasion_attempts"
        data["negotiation"]["rules"][22]["enforced_by"] = "product_notes"
        data["global_rules"][5]["enforced_by"] = "product_notes_skip"
        untagged = workflow_prompt_estimates(render(AB_FRESH)[0])["negotiate"]
        workflow, _, placements = render(data)
        self.assertLess(workflow_prompt_estimates(workflow)["negotiate"], untagged - 90)
        self.assertIn("(code: persuasion_attempts)", place(placements, "negotiation.rules[4]"))
        self.assertIn("(code: product_notes)", place(placements, "negotiation.rules[22]"))
        self.assertIn("(code: product_notes_skip)", place(placements, "global_rules[5]"))

    def test_new_checks_need_their_code_steps(self):
        spec = parse_spec(copy.deepcopy(AB_FRESH))
        for check in ("persuasion_attempts", "product_refusal", "product_notes", "product_notes_skip"):
            self.assertTrue(enforcement_available(spec, check), check)
            self.assertFalse(enforcement_available(spec, check, nodes={"negotiate"}), check)
        data = copy.deepcopy(AB_FRESH)
        data["offer"]["persuasion_attempts"] = []
        data["closing"].pop("product_notes")
        spec = parse_spec(data)
        self.assertFalse(enforcement_available(spec, "persuasion_attempts"))
        self.assertFalse(enforcement_available(spec, "product_notes"))
        self.assertTrue(enforcement_available(spec, "product_refusal"))

    def test_note_rule_stays_when_the_note_loop_is_not_rendered(self):
        data = copy.deepcopy(AB_FRESH)
        data["closing"].pop("product_notes")
        data["global_rules"][5]["enforced_by"] = "product_notes_skip"
        workflow, _, placements = render(data)
        self.assertIn("-> global prompt", place(placements, "global_rules[5]"))
        self.assertIn("tagged product_notes_skip but this spec has no data", place(placements, "global_rules[5]"))

    # Review finding 1: a negation, limit or alternative is never "plain words".
    def test_covering_keeps_negated_limited_or_flipped_rules(self):
        keep = [
            ("Ask once for the exact day of the payment.", "Don't ask once for the exact day of the payment."),
            ("Ask once for the exact day of the payment.", "You cannot ask once for the exact day of the payment."),
            ("Ask once for the exact day of the payment.", "If the period is vague, ask once for the exact day of the payment."),
            ("Offer the floor amount on the deadline date.", "Never offer the floor amount on the deadline date."),
            ("Offer the floor amount on the deadline date.", "Avoid offer the floor amount on the deadline date."),
            ("Offer the floor amount on the deadline date.", "Stop and offer the floor amount on the deadline date."),
            ("Offer the floor amount on the deadline date.", "Offer the floor amount on the deadline date or refuse instead."),
            ("Record the promise on the deadline date.", "Record the promise on the deadline date twice."),
            ("Record the promise on the deadline date.", "Record the promise on the deadline date for 2 products."),
        ]
        for shorter, longer in keep:
            data = copy.deepcopy(FIXTURE_A)
            data["negotiation"]["rules"] = [{"text": shorter, "source": "x"}, {"text": longer, "source": "x"}]
            _, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
            with self.subTest(longer=longer):
                self.assertIn("-> step negotiate", place(placements, "negotiation.rules[0]"))
        # Plain added words still count as covered.
        data = copy.deepcopy(FIXTURE_A)
        data["negotiation"]["rules"] = [
            {"text": "Treat a refusal of the floor as a flat refusal.", "source": "x"},
            {"text": "Treat a refusal of the floor as a flat refusal and use one attempt.", "source": "x"},
        ]
        _, _, placements = render(data, target_tokens=1, hard_limit_tokens=10_000)
        self.assertIn("duplicate of negotiation.rules[1]", place(placements, "negotiation.rules[0]"))

    # Review finding 2: the path carries out only what its own lines say.
    def test_special_path_rule_with_a_prohibition_or_extra_clause_stays(self):
        data = copy.deepcopy(AB_FRESH)
        path = next(item for item in data["special_paths"] if item["id"] == "human_request")
        rule = data["global_rules"][3]
        rule["text"] = "If the customer asks for a human, first ask once whether you can help."
        rule["source"] = path["ask"]["source"]
        _, _, placements = render(copy.deepcopy(data))
        self.assertIn("moved: was global; special path human_request", place(placements, "global_rules[3]"))  # control
        rule["source"] = "do not " + path["ask"]["source"]
        _, _, placements = render(copy.deepcopy(data))
        self.assertIn("-> global prompt (its section)", place(placements, "global_rules[3]"))
        data = copy.deepcopy(AB_FRESH)
        data["global_rules"][1]["text"] += " Never say this to anyone who has not been verified."
        workflow, _, placements = render(data)
        self.assertIn("-> global prompt (its section)", place(placements, "global_rules[1]"))
        self.assertIn("Never say this to anyone who has not been verified.", workflow["system_prompt"])

    def test_special_path_rule_needs_the_spoken_line(self):
        data = copy.deepcopy(AB_FRESH)
        path = next(item for item in data["special_paths"] if item["id"] == "scam_question")
        path["say"]["text"] = "Say that they can verify the call."  # agent-directed: the fallback is spoken
        _, _, placements = render(data)
        self.assertIn("-> global prompt", place(placements, "global_rules[1]"))
        data = copy.deepcopy(AB_FRESH)
        data["special_paths"] = [item for item in data["special_paths"] if item["id"] != "scam_question"]
        _, _, placements = render(data)
        self.assertIn("-> global prompt", place(placements, "global_rules[1]"))

    # Review finding 3: only a plain call of a code-run tool leaves the step.
    def test_code_tool_rule_with_speech_or_condition_stays(self):
        keep = [
            "Never tell the customer that add_note was called.",
            "Do not call add_note when a promise was recorded. Call add_note only after the customer "
            "confirmed they heard the reason.",
            "Call add_note only after the customer confirmed they heard the reason.",
            "Call add_note and tell the customer it is noted.",
        ]
        for text in keep:
            data = copy.deepcopy(AB_FRESH)
            data["negotiation"]["rules"][22]["text"] = text
            workflow, _, placements = render(data)
            with self.subTest(text=text):
                self.assertIn("-> step negotiate", place(placements, "negotiation.rules[22]"))
                self.assertIn(text, workflow["nodes"]["negotiate"]["task_message"])
        data = copy.deepcopy(AB_FRESH)
        data["negotiation"]["rules"][22]["text"] = "For each product, call add_note with its product_id and reason."
        _, _, placements = render(data)
        self.assertIn("(code: add_note is called by code (note_record), not by this step)",
                      place(placements, "negotiation.rules[22]"))

    # Review finding 4: "no notes on X" needs the skip list, and its own tag.
    def test_skip_rule_needs_skip_outcomes_and_its_own_tag(self):
        data = copy.deepcopy(AB_FRESH)
        data["closing"]["product_notes"]["skip_outcomes"] = []
        data["global_rules"][5]["enforced_by"] = "product_notes_skip"
        workflow, _, placements = render(data)
        self.assertIn("-> global prompt", place(placements, "global_rules[5]"))
        self.assertIn(AB_FRESH["global_rules"][5]["text"], workflow["system_prompt"])
        data = copy.deepcopy(AB_FRESH)
        data["global_rules"][5]["enforced_by"] = "product_notes"  # the wrong tag for a "no notes" rule
        workflow, _, placements = render(data)
        self.assertIn("tagged product_notes but it says more than that check does, kept",
                      place(placements, "global_rules[5]"))

    # Review finding 5: a tagged rule that says what to propose stays.
    def test_tagged_proposal_rule_stays(self):
        data = copy.deepcopy(AB_FRESH)
        for index in (13, 14, 15):  # "Attempt 1 is for the full past-due amount ...", "Attempt 1: propose ..."
            data["negotiation"]["rules"][index]["enforced_by"] = "persuasion_attempts"
        data["negotiation"]["rules"][5]["enforced_by"] = "persuasion_attempts"  # control: counting only
        workflow, _, placements = render(data)
        task = workflow["nodes"]["negotiate"]["task_message"]
        for index in (13, 14, 15):
            with self.subTest(index=index):
                self.assertIn("but it says more than that check does, kept", place(placements, f"negotiation.rules[{index}]"))
                self.assertIn(AB_FRESH["negotiation"]["rules"][index]["text"], task)
        self.assertIn("(code: persuasion_attempts)", place(placements, "negotiation.rules[5]"))


class SandboxPayloadTests(unittest.TestCase):
    """F-066: every code step and hook leaves room for the call variables."""

    def test_every_sandbox_run_fits_with_the_variable_reserve(self):
        for name, data in (("A", FIXTURE_A), ("AB", AB_TAGGED)):
            workflow, _, _ = render(data)
            payloads = workflow_code_payloads(workflow)
            with self.subTest(spec=name):
                self.assertIn("check_offer", payloads)
                self.assertIn("record_promise/create_promise.pre", payloads)
                self.assertIn("account/get_account.post", payloads)
                self.assertTrue(any(site.startswith("tools/") for site in payloads))
                self.assertEqual(sorted(payloads.values(), reverse=True), list(payloads.values()))
                for site, size in payloads.items():
                    self.assertLess(size, SANDBOX_PAYLOAD_LIMIT - VARIABLE_RESERVE_BYTES, site)


if __name__ == "__main__":
    unittest.main()
