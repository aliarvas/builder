"""T-025: replay the live extractor's output of PUB-11 (A+B, three products, all on one Friday).

The live call looped: the extractor never filled the product list number, check_offer said
product_unknown and wiped the offer every time (T-024). The replay feeds each recorded customer
turn, with exactly the fields the live extractor wrote, to the simulator at the step it waits at."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from builder.selfcheck import Bank, Simulator, _offer_loop_failures, _Plan, _promise_tool
from builder.spec import parse_spec
from builder.tools_from_openapi import CALL_VARIABLES
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import KIT_TOOLS

ROOT = Path(__file__).resolve().parents[1]
REPLAY = json.loads((ROOT / "tests/fixtures/replay/pub-11-extractions.json").read_text(encoding="utf-8"))
SPEC_DATA = json.loads((ROOT / "tests/fixtures/replay/brief-ab-live-spec.json").read_text(encoding="utf-8"))
OFFER_STEPS = ("negotiate", "offer_say", "revise_ask")


def replay(workflow, spec):
    """(simulator, step reached): the recorded negotiation turns, as the extractor wrote them."""
    now = REPLAY["now"]
    bank = Bank(spec, REPLAY["products"], {}, [])
    variables = {"now": now, spec.offer.data.get("today_variable") or "now": now}
    for name in CALL_VARIABLES:
        variables.setdefault(name, "sim-" + name)
    sim = Simulator(workflow, spec, bank, variables)
    for action in _Plan(spec, now).reach_negotiation():
        if action["kind"] == "say":
            sim.turn(dict(action["vars"]))
        else:
            sim.tool_turn(dict(action["args"]))
    first = next(index for index, turn in enumerate(REPLAY["turns"]) if turn["node"] == "negotiate")
    for turn in REPLAY["turns"][first:]:
        waiting = sim.advance()
        if waiting not in OFFER_STEPS:
            break
        # The extractor fills only the waiting step's fields; a turn with no route keeps it waiting.
        fields = {field["name"] for field in sim.nodes[waiting].get("extraction_schema") or []}
        sim.turn({name: value for name, value in turn["extracted"].items() if name in fields})
    return sim, sim.advance()


class ReplayPub11Tests(unittest.TestCase):
    def setUp(self):
        self.spec = parse_spec(SPEC_DATA.get("spec", SPEC_DATA))

    def test_the_recorded_turns_now_reach_the_read_back_and_three_promises(self):
        workflow = build_spec_workflow(self.spec, KIT_TOOLS)
        sim, step = replay(workflow, self.spec)
        self.assertEqual("confirm_record", step)
        self.assertEqual(3, int(sim.vars["offers_accepted_count"]))
        self.assertEqual([], _offer_loop_failures(sim))
        self.assertEqual(3, len(sim.offer_passes))  # one check per product, no product_unknown
        # The customer's "Yes, I confirm." at the read-back: the promises are recorded.
        confirmation = self.spec.confirmation.data
        value = next(v for v in confirmation["intent_values"] if v not in confirmation["revise_values"] and v != "none")
        sim.turn({confirmation["intent_variable"]: value, confirmation["expected_count_variable"]: 3})
        sim.advance()
        record = _promise_tool(workflow, self.spec)
        promises = sorted([str(call.body.get(confirmation["promise_product_id_field"])),
                           float(call.body.get(confirmation["promise_amount_field"])),
                           str(call.body.get(confirmation["promise_date_field"]))]
                          for call in sim.bank.calls if call.tool == record and call.ok)
        self.assertEqual(REPLAY["expected"]["promises"], promises)

    def test_the_old_check_loops_on_the_same_turns(self):
        # Before T-025 (no product picker): every check is product_unknown and the offer is lost.
        with mock.patch("builder.offer_check.multi_product", lambda spec: False), \
                mock.patch("builder.product_notes.multi_product", lambda spec: False):
            workflow = build_spec_workflow(self.spec, KIT_TOOLS)
        sim, step = replay(workflow, self.spec)
        self.assertEqual("offer_say", step)
        self.assertEqual(0, int(sim.vars["offers_accepted_count"]))
        self.assertGreaterEqual(len(sim.offer_passes), 4)
        self.assertEqual(1, len(_offer_loop_failures(sim)))


if __name__ == "__main__":
    unittest.main()
