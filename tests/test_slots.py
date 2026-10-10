from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from builder.slots import save_with_slot_check


class FakeClient:
    """Mimics the kit client's save_workflow and the workflow read route."""

    def __init__(self, existing):
        self.existing = set(existing)
        self.calls = []

    def workspace_id(self):
        return "ws"

    def api(self, method, path, body=None, **params):
        self.calls.append((method, path))
        workflow_id = path.rsplit("/", 1)[-1]
        if workflow_id == "boom":
            raise RuntimeError(f"{method} {path} -> 500: server error")
        if workflow_id not in self.existing:
            raise RuntimeError(f'{method} {path} -> 404: {{"message": "Workflow not found"}}')
        return {"workflow": {"id": workflow_id}}

    def save_workflow(self, slot, workflow, state_file=".freya-agents.json"):
        path = Path(state_file)
        state = json.loads(path.read_text()) if path.exists() else {}
        if slot in state:
            self.calls.append(("update", state[slot]["workflow_id"]))
        else:
            state[slot] = {"workflow_id": "new-id", "agent_id": "new-agent"}
            self.calls.append(("create", slot))
        path.write_text(json.dumps(state))
        return state[slot]


class SlotCheckTests(unittest.TestCase):
    def run_save(self, state, existing):
        with tempfile.TemporaryDirectory() as directory:
            state_file = str(Path(directory) / "slots.json")
            if state is not None:
                Path(state_file).write_text(json.dumps(state))
            client, warnings = FakeClient(existing), []
            saved = save_with_slot_check(client, "brief-a", {"nodes": {}}, state_file=state_file, warn=warnings.append)
            return saved, client.calls, warnings, json.loads(Path(state_file).read_text())

    def test_missing_stored_workflow_is_recreated_with_a_warning(self):
        saved, calls, warnings, state = self.run_save(
            {"brief-a": {"workflow_id": "gone", "agent_id": "a"}, "other": {"workflow_id": "x"}}, existing=[]
        )
        self.assertIn(("create", "brief-a"), calls)
        self.assertNotIn(("update", "gone"), calls)
        self.assertEqual("new-id", saved["workflow_id"])
        self.assertEqual(1, len(warnings))
        self.assertIn("gone", warnings[0])
        self.assertIn("other", state)

    def test_existing_stored_workflow_is_updated(self):
        saved, calls, warnings, _ = self.run_save({"brief-a": {"workflow_id": "w1", "agent_id": "a"}}, existing=["w1"])
        self.assertEqual([("GET", "/api/v2/workflow/w1"), ("update", "w1")], calls)
        self.assertEqual([], warnings)

    def test_no_slot_yet_creates_without_a_check(self):
        _, calls, warnings, _ = self.run_save(None, existing=[])
        self.assertEqual([("create", "brief-a")], calls)
        self.assertEqual([], warnings)

    def test_other_errors_are_not_treated_as_deleted(self):
        with self.assertRaisesRegex(RuntimeError, "-> 500"):
            self.run_save({"brief-a": {"workflow_id": "boom"}}, existing=[])

    def test_unreadable_slot_file_creates_with_a_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "slots.json"
            state_file.write_text("{broken")
            client, warnings = FakeClient([]), []
            save_with_slot_check(client, "brief-a", {}, state_file=str(state_file), warn=warnings.append)
            self.assertEqual([("create", "brief-a")], client.calls)
            self.assertEqual(1, len(warnings))


if __name__ == "__main__":
    unittest.main()
