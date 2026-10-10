"""T-009: prompt budget guard and rule placement (offline)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.spec import SpecError, parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import (
    PROMPT_HARD_LIMIT_TOKENS,
    PROMPT_TARGET_TOKENS,
    build_spec_workflow,
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
        self.assertLessEqual(max(estimates.values()), PROMPT_HARD_LIMIT_TOKENS)
        over = {key for key, value in estimates.items() if value > PROMPT_TARGET_TOKENS}
        self.assertEqual({"negotiate"}, over)  # see report: honest tags leave negotiate over the target
        self.assertTrue(any("negotiate: prompt" in warning and "over the target" in warning for warning in warnings))
        rule_lines = [line for line in placements if not line.startswith("budget")]
        placed = [line.split(" -> ")[0] for line in rule_lines]
        self.assertEqual(sorted(all_rule_keys(AB_TAGGED)), sorted(placed))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertIn("budget stages: code-enforced rules left out; duplicate wording removed", placements)
        self.assertTrue(any(line.startswith("budget negotiate: ~1595 -> ~13") for line in placements))

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

    def test_untagged_extraction_fails_clearly_instead_of_cutting_rules(self):
        with self.assertRaises(SpecError) as caught:
            render(AB)
        message = str(caught.exception)
        self.assertIn("prompt budget exceeded", message)
        self.assertIn("negotiate ~", message)
        self.assertIn("no policy rule is cut", message)

    def test_many_rules_trigger_the_guard_and_the_failure(self):
        data = copy.deepcopy(FIXTURE_A)
        data["negotiation"]["rules"] += [
            {"text": f"Synthetic policy rule number {i} with enough words to take real room in the prompt.", "source": "x"}
            for i in range(60)
        ]
        with self.assertRaises(SpecError):
            render(data)
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

    def test_unknown_enforcement_tag_is_a_spec_error(self):
        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["rules"] = [{"text": "x", "source": "x", "enforced_by": "magic"}]
        with self.assertRaises(SpecError):
            parse_spec(data)

    def test_tagged_closing_rule_needs_no_prompt(self):
        data = copy.deepcopy(FIXTURE_A)
        data["closing"]["rules"] = [
            {"text": "Call close_call exactly once, last.", "source": "x", "enforced_by": "closing_outcome"},
            {"text": "Add no notes on a transfer.", "source": "x"},
        ]
        workflow, _, placements = render(data)
        self.assertNotIn("close_call exactly once, last", workflow["system_prompt"])
        self.assertIn("Add no notes on a transfer.", workflow["system_prompt"])
        self.assertTrue(any(l.startswith("closing.rules[0] -> not in a prompt (code: closing_outcome)") for l in placements))


if __name__ == "__main__":
    unittest.main()
