"""F-061/F-062: per-product refusal and the code-owned note loop (offline)."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
import warnings
from pathlib import Path

from builder.product_notes import NOTES_DROPPED
from builder.spec import SpecError, parse_spec
from builder.workflow import build_spec_workflow, special_result_variable
from tests.test_multi_ready import AB_SPECS, CASES, Session, load
from tests.test_offer_date_only import TOOLS, code_of
from tests.test_multi_step import FIXTURES, graph, kit_tools

TAGGED = load(AB_SPECS["tagged"])
NEW_STEPS = {"product_refusal", "note_next", "note_record"}


def render(data, tools=TOOLS):
    return build_spec_workflow(parse_spec(copy.deepcopy(data)), tools)


def edges(node):
    return [transition["target_node"] for transition in node["transitions"]]


class SpecValidationTests(unittest.TestCase):
    def assertSpecError(self, change, text):
        data = copy.deepcopy(TAGGED)
        change(data)
        with self.assertRaises(SpecError) as caught:
            parse_spec(data)
        self.assertIn(text, str(caught.exception))

    def test_note_rule_values_are_checked(self):
        self.assertSpecError(lambda d: d["closing"]["product_notes"].update(refused_reason="nope"), "refused_reason")
        self.assertSpecError(lambda d: d["closing"]["product_notes"].update(failed_reason="nope"), "failed_reason")
        self.assertSpecError(lambda d: d["closing"]["product_notes"].update(skip_outcomes=["moved"]), "skip_outcomes")
        self.assertSpecError(lambda d: d["closing"]["product_notes"].update(reasons=[]), "reasons")
        self.assertSpecError(lambda d: d["closing"]["product_notes"].update(extra=1), "unknown keys")

    def test_refusal_values_are_checked(self):
        self.assertSpecError(lambda d: d["negotiation"].update(product_end_values=["agreed_date_and_amount"]),
                             "product_end_values must be close_values")
        self.assertSpecError(lambda d: d["negotiation"].update(attempt_values=["refuses_to_talk"]),
                             "attempt_values must be")
        self.assertSpecError(lambda d: d["negotiation"].update(product_end_values=[]), "needs product_end_values")
        self.assertSpecError(lambda d: d["negotiation"].update(attempt_values=[]), "needs negotiation.attempt_values")
        self.assertSpecError(lambda d: d["offer"]["persuasion_attempts"][0].update(value=0), "persuasion_attempts[0].value")

    def test_a_note_tool_the_api_cannot_carry_drops_the_block(self):
        for change, text in (
            (lambda d: d["closing"]["product_notes"].update(tool="write_memo"), "not an OpenAPI tool"),
            (lambda d: d["closing"]["product_notes"].update(product_field="item"), "not a add_note body field"),
            (lambda d: (d["closing"]["product_notes"]["reasons"].append("lost"),
                        d["closing"]["product_notes"].update(refused_reason="lost")), "not in the add_note enum"),
        ):
            # Review finding 2: the optional note block is dropped with a warning; the build goes on.
            data = copy.deepcopy(TAGGED)
            change(data)
            warnings = []
            workflow = build_spec_workflow(parse_spec(copy.deepcopy(data)), TOOLS, warnings)
            self.assertFalse({"note_next", "note_record"} & set(workflow["nodes"]))
            self.assertEqual(["closing_say"], edges(workflow["nodes"]["closing"]))
            dropped = [warning for warning in warnings if warning.startswith(NOTES_DROPPED)]
            self.assertEqual(1, len(dropped), warnings)
            self.assertIn(text, dropped[0])
            self.assertIn("product_refusal", workflow["nodes"])  # the rest of the feature stays


class StructureTests(unittest.TestCase):
    def test_every_fixture_has_the_steps_only_when_its_spec_asks(self):
        specs = [(path, kit_tools(index)) for index, path in enumerate(FIXTURES)]
        specs += [(path, TOOLS) for path in AB_SPECS.values()]
        for path, tools in specs:
            with self.subTest(spec=path.name):
                data = load(path)
                workflow = render(data, tools)
                nodes = workflow["nodes"]
                notes = (data["closing"].get("product_notes") or None) is not None
                refusal = bool(data["negotiation"].get("product_end_values"))
                self.assertEqual(notes, "note_next" in nodes and "note_record" in nodes)
                self.assertEqual(refusal, "product_refusal" in nodes)
                self.assertEqual(["note_next"] if notes else ["closing_say"], edges(nodes["closing"]))
                if notes:
                    record = nodes["note_record"]
                    # F-050: a silent passthrough api step; the tool is filled by code only.
                    self.assertEqual(("api_request", {"type": "silent"}, True),
                                     (record["node_type"], record["on_enter"], record["passthrough"]))
                    self.assertEqual("always", record["transitions"][-1]["condition"]["operator"])
                    body = record["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
                    note = data["closing"]["product_notes"]
                    self.assertEqual("{{note_product_id}}", body[note["product_field"]]["default"])
                    self.assertEqual("{{note_reason}}", body[note["reason_field"]]["default"])
                    self.assertTrue(all(prop.get("default", "").startswith("{{") for prop in body.values()))
                    self.assertNotIn("text", body)  # no model fills it here
                    # T-011: the outcome from the notes runs after the loop when the spec has it.
                    derived = bool(note.get("outcome_from_notes"))
                    self.assertEqual(derived, "notes_outcome" in nodes)
                    self.assertEqual(["note_record", "notes_outcome" if derived else "closing_say"],
                                     edges(nodes["note_next"]))
                    self.assertNotIn("tts", json.dumps([nodes["note_next"]["on_enter"], record["on_enter"]]))
                if refusal:
                    for key in ("negotiate", "offer_say", "revise_ask"):
                        self.assertEqual("product_refusal", edges(nodes[key])[1], key)
                    self.assertEqual(["offer_say", "confirm_record", "closing", "negotiate"],
                                     edges(nodes["product_refusal"]))
                # The new steps are reachable only from where they are meant to be.
                for source, targets in graph(workflow).items():
                    if "note_next" in targets:
                        self.assertIn(source, {"closing", "note_record"})
                    if "product_refusal" in targets:
                        self.assertIn(source, {"negotiate", "offer_say", "revise_ask"})

    def test_brief_a_is_unchanged(self):
        # Fixture A has no note rule and no per-product refusal: the old routes, no new step,
        # and the negotiate prompt has no attempt line.
        workflow = render(load(FIXTURES[0]))
        nodes = workflow["nodes"]
        self.assertFalse(NEW_STEPS & set(nodes))
        self.assertEqual(["check_offer", "confirm_record", "closing"], edges(nodes["negotiate"]))
        self.assertEqual(["closing_say"], edges(nodes["closing"]))
        self.assertNotIn("persuasion_attempt", nodes["negotiate"]["task_message"])


class NoteLoopTests(unittest.TestCase):
    def accepted_three(self):
        session = Session(AB_SPECS["tagged"], CASES["PUB-11"])
        for number in (1, 2, 3):
            session.say(offer_date="this Friday", offer_product_number=number)
        self.assertEqual("confirm_record", session.step)
        return session

    def test_failed_promise_gets_the_failed_reason(self):
        # Brief B rule 11: the recorded promises stay; the failed product gets service_error.
        session = self.accepted_three().record_all(answers=[True, True, False, False])
        self.assertEqual(2, len(session.promises))
        self.assertEqual("promise", session.close()[0])
        self.assertEqual([("p3", "service_error")], session.ledger_notes())

    def test_transfer_adds_no_notes(self):
        # Brief B rule 10: a transfer (outcome in skip_outcomes) gets no notes at all.
        session = Session(AB_SPECS["tagged"], CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        path = next(path for path in parse_spec(copy.deepcopy(TAGGED)).special_paths if path.id == "human_request")
        session.vars[special_result_variable(path)] = "true"
        session.step = "closing"
        self.assertEqual("transferred", session.close()[0])
        self.assertEqual([], session.note_calls)
        self.assertEqual("closing_say", session.step)

    def test_no_promise_notes_every_product(self):
        session = Session(AB_SPECS["fixture-b"], CASES["PUB-12"])
        refusal = session.refusal()
        for _ in range(3):
            session.say(**refusal)
        self.assertEqual("closing", session.step)
        self.assertEqual(("no_promise", "refused"), session.close())
        self.assertEqual([("p1", "refused"), ("p2", "refused"), ("p3", "refused")], session.ledger_notes())

    def test_a_failing_note_is_retried_once_then_skipped(self):
        session = Session(AB_SPECS["fixture-b"], CASES["PUB-13"])
        refusal = session.refusal()
        session.say(**refusal)
        session.say(**refusal)
        session.close(note_answers=[False, False])
        self.assertEqual(["p1", "p1", "p2"], [call["product_id"] for call in session.note_calls])
        self.assertEqual([("p2", "refused")], session.ledger_notes())
        self.assertEqual("closing_say", session.step)

    def test_a_note_written_on_a_special_path_is_not_repeated(self):
        # Dispute on the loan (special path, the model writes add_note), then the other two end.
        session = Session(AB_SPECS["tagged"], CASES["PUB-12"])
        spec = parse_spec(copy.deepcopy(TAGGED))
        dispute = next(path for path in spec.special_paths if path.id == "dispute")
        number_field = spec.confirmation.data["product_number_field"]
        session.vars[special_result_variable(dispute)] = "true"
        session.vars["add_note_args." + number_field] = 2
        exec(code_of(session.nodes["special_dispute_done"]), {"vars": session.vars})
        self.assertEqual([2], json.loads(session.vars["notes_written"]))
        session.end_product()  # product 1
        session.end_product()  # product 3 (2 is handled)
        self.assertEqual("closing", session.step)
        session.close()
        self.assertEqual([("p1", "refused"), ("p3", "refused")], session.ledger_notes())

    def test_a_closing_special_path_note_counts_and_its_reason_applies(self):
        # Hardship declined closes the call after the model noted one product (by its number):
        # that product is not noted again; the others take the call's reason, hardship.
        session = Session(AB_SPECS["tagged"], CASES["PUB-12"])
        spec = parse_spec(copy.deepcopy(TAGGED))
        declined = next(path for path in spec.special_paths if path.id == "hardship_declined")
        session.vars[special_result_variable(declined)] = "true"
        session.vars["add_note_args." + spec.confirmation.data["product_number_field"]] = 1
        session.step = "closing"
        self.assertEqual(("no_promise", "hardship"), session.close())
        self.assertEqual([("p2", "hardship"), ("p3", "hardship")], session.ledger_notes())


    def test_an_accepted_offer_never_sent_takes_the_close_reason(self):
        # AB-FRESH risk 3: the card is accepted, then hardship is declined before the read-back.
        # No record call was made, so the card is noted hardship, not the failed reason.
        session = Session(AB_SPECS["v2"], CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        session.vars["close_state"] = "special:hardship_declined"  # the path's code step
        session.step = "closing"
        self.assertEqual(("no_promise", "hardship"), session.close())
        self.assertEqual([("p1", "hardship"), ("p2", "hardship"), ("p3", "hardship")], session.ledger_notes())

    def test_a_product_whose_record_call_failed_keeps_the_failed_reason(self):
        for name in ("tagged", "v2"):
            with self.subTest(spec=name):
                session = Session(AB_SPECS[name], CASES["PUB-11"])
                for number in (1, 2, 3):
                    session.say(offer_date="this Friday", offer_product_number=number)
                session.record_all(answers=[False, False, True, True])
                self.assertEqual("promise", session.close()[0])
                self.assertEqual([("p1", "service_error")], session.ledger_notes())


class GeneratedCodeTests(unittest.TestCase):
    def test_builder_and_generated_code_compile_without_escape_warnings(self):
        # AB-FRESH risk 4: an invalid escape (a regex inside a code template string) is a
        # SyntaxWarning today and an error in later Python versions.
        sources = {path.name: path.read_text(encoding="utf-8")
                   for path in (Path(__file__).resolve().parents[1] / "builder").glob("*.py")}
        for name, path in AB_SPECS.items():
            workflow = build_spec_workflow(parse_spec(copy.deepcopy(load(path))), TOOLS)
            for key, node in {**workflow["nodes"], **workflow.get("global_nodes", {})}.items():
                if node.get("node_type") == "code":
                    sources[name + ":" + key] = code_of(node)
        for name, source in sources.items():
            with self.subTest(source=name), warnings.catch_warnings():
                warnings.simplefilter("error", SyntaxWarning)
                compile(source, name, "exec")


class RefusalChoiceTests(unittest.TestCase):
    def test_the_product_the_customer_names_is_the_one_refused(self):
        # Review finding 4: "the car loan is the one I cannot pay" while the loan is next.
        session = Session(AB_SPECS["tagged"], CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        session.end_product({"offer_product_number": 3, "negotiation_reply": "refused_attempts_exhausted"})
        self.assertEqual({"3": 1}, json.loads(session.vars["persuasion_used_by_product"]))  # the car loan's one attempt
        self.assertEqual({"3": "refused"}, json.loads(session.vars["product_note_reasons"]))
        self.assertEqual("offer_say", session.step)
        self.assertIn(session.named("personal loan", "second"), session.vars["offer_message"])  # the next open one

    def test_a_named_product_already_handled_falls_back_to_account_order(self):
        session = Session(AB_SPECS["tagged"], CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        session.end_product({"offer_product_number": 1, "negotiation_reply": "refused_attempts_exhausted"})
        self.assertEqual({"2": "refused"}, json.loads(session.vars["product_note_reasons"]))

    def test_no_matching_attempt_rule_ends_the_product(self):
        # Review finding 5: a band gap (no rule for the loan's days late) closes the product
        # instead of persuading without end.
        data = copy.deepcopy(TAGGED)
        data["offer"]["persuasion_attempts"] = data["offer"]["persuasion_attempts"][:1]  # early band only
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gap.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            session = Session(path, CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        session.say(negotiation_reply="refusal_attempts_left")  # the loan (days late 16): no rule
        self.assertEqual({"2": "refused"}, json.loads(session.vars["product_note_reasons"]))
        self.assertEqual("offer_say", session.step)
        session.say(negotiation_reply="refusal_attempts_left")  # the car loan (early band): one attempt
        self.assertEqual(("negotiate", 1), (session.step, session.vars["persuasion_attempt"]))


if __name__ == "__main__":
    unittest.main()
