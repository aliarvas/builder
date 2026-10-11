"""T-023: special paths behind a step's own routes (PUB-08) and the answer to a path's
question (PUB-05), rendered and played by the self-check."""

from __future__ import annotations

import copy
import json
import unittest

from builder.extract import merge_groups
from builder.selfcheck import BUILDER, play, run_selfcheck, scenarios, shadowed_intent_steps
from builder.spec import SpecError, parse_spec
from builder.workflow import SPECIAL_STAY, SPECIAL_TOPIC_VALUE, build_spec_workflow, choice_variables
from tests.test_selfcheck import SPECS, load
from tests.test_selfcheck_families import AB, BRIEF_A, failed, render

NOW = "2026-10-14T11:00"


def without_topic(workflow):
    """The version 18 render: no special-topic value in any choice field."""
    for node in workflow["nodes"].values():
        for field in node.get("extraction_schema") or []:
            if SPECIAL_TOPIC_VALUE in field.get("enum_values", []):
                field["enum_values"].remove(SPECIAL_TOPIC_VALUE)


def ab_data():
    path, _ = SPECS[AB]
    data = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(data.get("spec", data))


def with_decline(data):
    """The A+B spec with the brief's link: a no to the support question is the hardship close."""
    for path in data["special_paths"]:
        if path["id"] == "hardship_support":
            path["on_decline"] = "hardship_declined"
    return data


class SpecialTopicRenderTests(unittest.TestCase):
    def test_choice_fields_offer_the_value_and_name_the_situations(self):
        spec, workflow = render(AB)
        whens = {path.id: path.when.text.rstrip(".") for path in spec.special_paths}
        negotiate = next(field for field in workflow["nodes"]["negotiate"]["extraction_schema"]
                         if field["name"] == spec.negotiation.data["intent_variable"])
        self.assertIn(SPECIAL_TOPIC_VALUE, negotiate["enum_values"])
        self.assertEqual("none", negotiate["enum_values"][-1])  # the system value stays last
        for path_id in ("already_paid", "dispute", "hardship_support", "robot_question"):
            self.assertIn(whens[path_id], negotiate["description"])
        # Only the paths that can start at the step are named (no promise talk at the opening).
        opening = next(field for field in workflow["nodes"]["opening"]["extraction_schema"]
                       if field["name"] in choice_variables(spec))
        self.assertIn(whens["robot_question"], opening["description"])
        self.assertNotIn(whens["already_paid"], opening["description"])
        # No step route takes the value: the platform goes on to the intents.
        self.assertEqual([], shadowed_intent_steps(spec, workflow))

    def test_a_step_without_intent_paths_gets_no_value(self):
        spec, workflow = render(BRIEF_A)
        for key, node in workflow["nodes"].items():
            starts = [name for name, other in workflow["global_nodes"].items()
                      if key not in other.get("excluded_nodes", [])]
            if not starts:
                for field in node.get("extraction_schema") or []:
                    self.assertNotIn(SPECIAL_TOPIC_VALUE, field.get("enum_values", []), key)


class SpecialTopicSelfCheckTests(unittest.TestCase):
    def test_the_family_passes_on_every_fixture(self):
        for name in SPECS:
            spec, workflow = render(name)
            ids = {s.id for s in scenarios(spec, NOW) if "_over_choice_at_" in s.id}
            with self.subTest(spec=name):
                self.assertTrue(ids)
                self.assertEqual({}, failed(spec, workflow, ids, NOW))

    def test_the_version_18_render_is_caught_by_the_family_and_the_static_check(self):
        # PUB-08: "I paid it in the app" read as a refusal; product_refusal wins over already_paid.
        for name in (BRIEF_A, AB):  # Brief A: already_paid closes; A+B: it notes and goes on
            spec, workflow = render(name)
            without_topic(workflow)
            ids = {s.id for s in scenarios(spec, NOW) if "_over_choice_at_" in s.id}
            result = failed(spec, workflow, ids, NOW)
            with self.subTest(spec=name):
                self.assertEqual(ids, set(result))
                self.assertIn("never starts", " ".join(result["special_already_paid_over_choice_at_negotiate"]))
        steps = {step for step, _ in shadowed_intent_steps(spec, workflow)}
        self.assertTrue({"negotiate", "offer_say", "confirm_record", "opening"} <= steps, steps)
        report = run_selfcheck(spec, workflow, NOW)
        self.assertIn("intent_shadow[negotiate]", {r.scenario for r in report.builder_problems})

    def test_a_route_that_takes_the_value_is_caught(self):
        spec, workflow = render(AB)
        node = workflow["nodes"]["negotiate"]
        variable = spec.negotiation.data["intent_variable"]
        node["transitions"].insert(0, {"target_node": "product_refusal", "description": "mutation", "condition": {
            "logic": "or", "conditions": [{"variable": variable, "operator": "equals", "operand": SPECIAL_TOPIC_VALUE}]}})
        problems = dict(shadowed_intent_steps(spec, workflow))
        self.assertIn("a step route takes", problems["negotiate"])

    def test_a_situation_left_out_of_the_description_is_caught(self):
        spec, workflow = render(BRIEF_A)
        field = next(f for f in workflow["nodes"]["negotiate"]["extraction_schema"]
                     if f["name"] == spec.negotiation.data["intent_variable"])
        already = next(p for p in spec.special_paths if p.id == "already_paid").when.text.rstrip(".")
        field["description"] = field["description"].replace(already, "something else")
        self.assertIn("not named", dict(shadowed_intent_steps(spec, workflow))["negotiate"])
        result = failed(spec, workflow, {"special_already_paid_over_choice_at_negotiate"}, NOW)
        self.assertIn("special_already_paid_over_choice_at_negotiate", result)

    def test_the_platform_order_is_modelled(self):
        # A turn that a step route takes never reaches the intent, also when the intent matches.
        spec, workflow = render(BRIEF_A)
        without_topic(workflow)
        scenario = next(s for s in scenarios(spec, NOW) if s.id == "special_dispute_over_choice_at_negotiate")
        sim, failures = play(workflow, spec, scenario, NOW)
        self.assertNotIn("special_dispute", sim.path)
        self.assertIn("negotiate", sim.path)  # the step's refusal route took the turn
        self.assertTrue(any("never starts" in failure for failure in failures))


class SpecialChoiceTests(unittest.TestCase):
    def test_the_choice_follows_what_going_ahead_does(self):
        # PUB-05: "I do not want to be transferred" was read as proceed. The description now says
        # what proceed does, so a no to "connect you?" and a no to "help you first?" read right.
        spec, workflow = render(AB)
        support = workflow["global_nodes"]["special_hardship_support"]["extraction_schema"][0]["description"]
        human = workflow["global_nodes"]["special_human_request"]["extraction_schema"][0]["description"]
        for text, path_id in ((support, "hardship_support"), (human, "human_request")):
            path = next(p for p in spec.special_paths if p.id == path_id)
            self.assertIn(path.ask.text, text)
            self.assertIn(f"call {path.tool} (", text)
            self.assertIn("not by the word yes or no", text)
        self.assertNotIn("insists", support)

    def test_without_on_decline_a_no_goes_back(self):
        spec, workflow = render(AB)
        stay = [t for t in workflow["global_nodes"]["special_hardship_support"]["transitions"]
                if any(c.get("operand") == SPECIAL_STAY for c in t["condition"]["conditions"])]
        self.assertEqual(["__previous__"], [t["target_node"] for t in stay])
        self.assertNotIn("special_hardship_support_declined", {s.id for s in scenarios(spec, NOW)})

    def test_on_decline_closes_on_the_named_path(self):
        spec = parse_spec(with_decline(ab_data()))
        workflow = build_spec_workflow(spec, SPECS[AB][1])
        node = workflow["global_nodes"]["special_hardship_support"]
        stay = [t["target_node"] for t in node["transitions"]
                if any(c.get("operand") == SPECIAL_STAY for c in t["condition"]["conditions"])]
        self.assertEqual(["special_hardship_support_declined"], stay)
        declined = workflow["nodes"]["special_hardship_support_declined"]
        self.assertNotIn("condition", declined)  # a plain step, entered only from the question
        # Freya rejects "description" on a plain node (live v19 build: "Unrecognized key").
        self.assertNotIn("description", declined)
        for key, plain in workflow["nodes"].items():
            self.assertNotIn("description", plain, key)
            self.assertNotIn("condition", plain, key)
        ids = {s.id for s in scenarios(spec, NOW)}
        self.assertIn("special_hardship_support_declined", ids)
        # The decline is the hardship close; the ask-first path no longer counts as returning.
        self.assertFalse([i for i in ids if i.startswith("special_hardship_support_then_")])
        report = run_selfcheck(spec, workflow, NOW)
        self.assertEqual([], [r for r in report.results if not r.passed and "hardship" in r.scenario])
        scenario = next(s for s in scenarios(spec, NOW) if s.id == "special_hardship_support_declined")
        self.assertEqual(("no_promise", "hardship"), scenario.pair)

    def test_a_no_that_goes_back_instead_is_caught(self):
        spec = parse_spec(with_decline(ab_data()))
        workflow = build_spec_workflow(spec, SPECS[AB][1])
        for transition in workflow["global_nodes"]["special_hardship_support"]["transitions"]:
            if transition["target_node"] == "special_hardship_support_declined":
                transition["target_node"] = "__previous__"  # the version 18 behaviour
        result = failed(spec, workflow, {"special_hardship_support_declined"}, NOW)
        self.assertIn("special_hardship_support_declined", result)

    def test_on_decline_must_name_another_closing_path(self):
        for target in ("missing", "hardship_support", "human_request", "robot_question"):
            data = ab_data()
            for path in data["special_paths"]:
                if path["id"] == "hardship_support":
                    path["on_decline"] = target
            with self.subTest(target=target), self.assertRaisesRegex(SpecError, "on_decline"):
                parse_spec(data)
        data = ab_data()
        for path in data["special_paths"]:
            if path["id"] == "hardship_declined":
                path["on_decline"] = "dispute"  # a path without ask
        with self.assertRaisesRegex(SpecError, "on_decline"):
            parse_spec(data)

    def test_extraction_drops_an_on_decline_it_cannot_use(self):
        from tests.test_callback import groups_from_spec

        data = with_decline(ab_data())
        for path in data["special_paths"]:
            if path["id"] == "human_request":
                path["on_decline"] = "robot_question"  # a returning path: dropped
        groups = groups_from_spec(data)
        merged = merge_groups(groups)
        by_id = {path["id"]: path for path in merged["special_paths"]}
        self.assertEqual("hardship_declined", by_id["hardship_support"]["on_decline"])
        self.assertNotIn("on_decline", by_id["human_request"])
        parse_spec(merged)


if __name__ == "__main__":
    unittest.main()
