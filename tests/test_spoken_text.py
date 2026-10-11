"""F-047 (spoken fields must address the customer) and F-048 (introduction only in the opening)."""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from builder.extract import SPOKEN_MARK, extract_spec
from builder.prompts import ACCOUNT_WAIT_LINE, CLOSING_FALLBACK_SAY, SPECIAL_SAY_FALLBACK
from builder.spec import parse_spec
from builder.spoken import agent_directed, present_recording_notice, spoken_words
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow
from tests.extract_helpers import FakeClient, as_text
from tests.test_extract import BRIEF_A, OPENAPI, RECORDED_A, replies_for

ROOT = Path(__file__).resolve().parents[1]
TOOLS = tools_from_openapi(OPENAPI)
FIXTURE_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
# Live extraction of version 11 (F-047): 14 spoken fields were instructions.
V11 = json.loads((ROOT / "tests/fixtures/extract/brief-a-v11-extracted.json").read_text(encoding="utf-8"))


def spoken_texts(workflow):
    """Every fixed line the workflow can speak: tts entries and the closing sentences."""
    texts = []
    for node in [*workflow["nodes"].values(), *workflow["global_nodes"].values()]:
        if node.get("on_enter", {}).get("type") == "tts":
            texts.append(node["on_enter"]["text"])
    code = workflow["nodes"]["closing"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    # The outcome table and the special-path lines said before it (F-056/F-059).
    for marker in ("TABLE = [", "FIRST_LINES = ["):
        start = code.index(marker)
        table = code[start:code.index("\n]\n", start)]
        texts += [text for text in re.findall(r'"((?:[^"\\\\]|\\\\.)*)"', table) if " " in text]
    return [text for text in texts if "{{" not in text]


def render(data):
    warnings = []
    return build_spec_workflow(parse_spec(copy.deepcopy(data)), TOOLS, warnings), warnings


class DetectorTests(unittest.TestCase):
    SPEECH = [
        "Thank you for speaking with me today. Goodbye.", "You will receive a text message confirming this promise.",
        "Before I transfer you, is there anything I can help you with myself?", "Please use the mobile app or visit a branch.",
        "Would you like me to connect you with the customer support team?", "I am sorry for your loss.",
        "Call us back on the number on your card.", "I understand. I will not ask you for a payment today.",
    ]
    INSTRUCTIONS = [
        "Thank the customer and say goodbye.", "Say goodbye.", "Tell the customer to use the mobile app.",
        "Offer to connect them with the support team.", "Do not argue.", "Ask once whether you can help first.",
        "Close as no_promise / refused.", "Say that payments can take one business day to appear.", "Take no promise.",
        "Thank you. Then say goodbye.",
    ]

    def test_speech_passes_and_instructions_are_caught(self):
        for text in self.SPEECH:
            self.assertEqual("", agent_directed(text), text)
        for text in self.INSTRUCTIONS:
            self.assertNotEqual("", agent_directed(text), text)

    def test_say_wrapper_is_unwrapped(self):
        self.assertEqual("You will receive a text message.", spoken_words('Say: "You will receive a text message."'))
        self.assertEqual("A letter will be sent.", spoken_words("Say: A letter will be sent."))
        self.assertEqual("Say that it was sent.", spoken_words("Say that it was sent."))


class RendererFallbackTests(unittest.TestCase):
    def test_live_v11_spec_speaks_no_instruction(self):
        workflow, warnings = render(V11)
        texts = spoken_texts(workflow)
        self.assertTrue(texts)
        self.assertEqual([], [text for text in texts if agent_directed(text)])
        self.assertIn(CLOSING_FALLBACK_SAY.text, texts)
        self.assertGreaterEqual(sum(1 for w in warnings if w.startswith("spoken_fallback outcomes[")), 11)

    def test_reference_spec_is_unchanged(self):
        workflow, warnings = render(FIXTURE_A)
        self.assertFalse([w for w in warnings if w.startswith("spoken_fallback")])
        self.assertIn("You will receive a text message confirming this promise.", " ".join(spoken_texts(workflow)))

    def test_each_spoken_field_has_its_fallback(self):
        data = copy.deepcopy(FIXTURE_A)
        data["outcomes"][0]["say"]["text"] = 'Say: "You will receive a text message. Goodbye."'
        data["outcomes"][1]["say"]["text"] = "Thank the customer and say goodbye."
        data["special_paths"][0]["say"]["text"] = "Say that payments can take a day to appear."
        data["special_paths"][2]["ask"]["text"] = "Ask once whether you can help first."
        data["agent"]["wait_line"] = "Tell the customer to wait."
        workflow, warnings = render(data)
        texts = spoken_texts(workflow)
        self.assertIn("You will receive a text message. Goodbye.", texts)  # unwrapped, no fallback
        self.assertIn(CLOSING_FALLBACK_SAY.text, texts)
        self.assertIn(SPECIAL_SAY_FALLBACK.text, texts)
        self.assertIn("then say: " + ACCOUNT_WAIT_LINE.text, workflow["nodes"]["identity"]["task_message"])
        ask_node = next(node for node in workflow["global_nodes"].values()
                        if "Ask once whether you can help first." in node.get("task_message", ""))
        self.assertEqual({"type": "llm"}, ask_node["on_enter"])
        self.assertIn("in your own words", ask_node["task_message"])
        for where in ("outcomes[1].say", "special_paths[0].say", "special_paths[2].ask", "agent.wait_line"):
            self.assertTrue(any(w.startswith(f"spoken_fallback {where}:") for w in warnings), where)
        self.assertFalse(any(w.startswith("spoken_fallback outcomes[0]") for w in warnings))


class ExtractionSpokenTests(unittest.TestCase):
    def broken_outcomes(self):
        broken = copy.deepcopy(RECORDED_A["outcomes"])
        broken["outcomes"][1]["say"]["text"] = "Thank the customer and say goodbye."
        return broken

    def test_instruction_is_sent_back_for_repair(self):
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A, outcomes=[as_text(self.broken_outcomes()),
                                                                       as_text(RECORDED_A["outcomes"])]))
        extract_spec(BRIEF_A, OPENAPI, client)
        repair = next(messages[-1]["content"] for purpose, messages in client.calls if purpose == "repair1:outcomes")
        self.assertIn("outcomes[1].say: " + SPOKEN_MARK, repair)
        self.assertIn("not an instruction to the agent", repair)

    def test_never_fixed_instruction_does_not_stop_the_build(self):
        logs = []
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A, outcomes=[as_text(self.broken_outcomes())]))
        result = extract_spec(BRIEF_A, OPENAPI, client, log=lambda key, value: logs.append((key, str(value))))
        self.assertEqual(2, sum(1 for p in client.purposes() if p.startswith("repair")))
        self.assertTrue(any(key == "extract_warning" and SPOKEN_MARK in value for key, value in logs))
        workflow, warnings = render(result.spec_data)
        self.assertIn(CLOSING_FALLBACK_SAY.text, spoken_texts(workflow))
        self.assertTrue(any(w.startswith("spoken_fallback outcomes[1].say") for w in warnings))

    def test_introduction_and_exhausted_line_must_be_words(self):
        broken = copy.deepcopy(RECORDED_A["opening_identity"])
        broken["agent"]["introduction"]["text"] = "Say you are a digital assistant calling from the bank."
        broken["identity"]["exhausted_say"]["text"] = "Tell the customer to use the mobile app."
        client = FakeClient(replies_for(RECORDED_A, BRIEF_A, opening_identity=[as_text(broken),
                                                                               as_text(RECORDED_A["opening_identity"])]))
        extract_spec(BRIEF_A, OPENAPI, client)
        repair = next(messages[-1]["content"] for purpose, messages in client.calls
                      if purpose == "repair1:opening_identity")
        self.assertIn("agent.introduction: " + SPOKEN_MARK, repair)
        self.assertIn("identity.exhausted_say: " + SPOKEN_MARK, repair)


class IdentityEntryTests(unittest.TestCase):
    """F-049: entering the identity step with identity already verified goes straight on."""

    def test_opening_goes_through_the_identity_check(self):
        workflow, _ = render(FIXTURE_A)
        nodes = workflow["nodes"]
        opening_targets = {t["target_node"] for t in nodes["opening"]["transitions"]}
        self.assertIn("identity_check", opening_targets)
        self.assertNotIn("identity", opening_targets)
        check = nodes["identity_check"]
        self.assertEqual("code", check["node_type"])
        self.assertTrue(check["passthrough"])
        self.assertEqual({"type": "silent"}, check.get("on_enter", {"type": "silent"}))
        first, last = check["transitions"][0], check["transitions"][-1]
        self.assertEqual("account", first["target_node"])
        self.assertEqual({("identity_verified", "equals", "true"), ("identity_verified", "equals", "True")},
                         {(c["variable"], c["operator"], c["operand"]) for c in first["condition"]["conditions"]})
        self.assertEqual(("identity", "always"), (last["target_node"], last["condition"]["operator"]))

    def test_check_routes_by_the_verified_variable(self):
        workflow, _ = render(FIXTURE_A)
        check = workflow["nodes"]["identity_check"]

        def route(variables):
            for transition in check["transitions"]:
                condition = transition["condition"]
                if condition.get("operator") == "always":
                    return transition["target_node"]
                if any(variables.get(c["variable"]) == c["operand"] for c in condition["conditions"]):
                    return transition["target_node"]

        self.assertEqual("account", route({"identity_verified": "true"}))
        self.assertEqual("account", route({"identity_verified": "True"}))
        self.assertEqual("identity", route({"identity_verified": "false"}))
        self.assertEqual("identity", route({}))


class IntroductionPlacementTests(unittest.TestCase):
    def test_introduction_is_only_in_the_opening(self):
        for data in (FIXTURE_A, V11):
            workflow, _ = render(data)
            introduction = present_recording_notice(parse_spec(copy.deepcopy(data)).agent.introduction.text)[0]  # T-026
            self.assertNotIn(introduction, workflow["system_prompt"])
            self.assertIn(introduction, workflow["nodes"]["opening"]["task_message"])
            self.assertNotIn(introduction, workflow["nodes"]["third_party"]["task_message"])
            self.assertNotIn("not yet given this introduction", workflow["system_prompt"])


if __name__ == "__main__":
    unittest.main()
