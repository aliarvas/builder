"""Workflow slot handling around the kit client (F-005).

``freya.save_workflow`` trusts the local slot file. If the stored workflow was deleted on
the platform, the update fails. This wrapper checks the stored ID first and, if it is
gone, drops the stale entry so ``save_workflow`` creates a new workflow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

STATE_FILE = ".freya-agents.json"


def _is_not_found(error: BaseException) -> bool:
    # freya.api raises RuntimeError("GET <path> -> <code>: <body>").
    return "-> 404" in str(error)


def save_with_slot_check(
    client: Any, slot: str, workflow: dict[str, Any], *,
    state_file: str = STATE_FILE, warn: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    """Save ``workflow`` into ``slot``; recreate it if the stored workflow no longer exists."""
    path = Path(state_file)
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
        warn(f"slot file {state_file} is unreadable; a new workflow will be created")
        path.write_text("{}", encoding="utf-8")
    stored = state.get(slot) if isinstance(state, dict) else None
    workflow_id = stored.get("workflow_id") if isinstance(stored, dict) else None
    if workflow_id:
        try:
            client.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=client.workspace_id())
        except RuntimeError as error:
            if not _is_not_found(error):
                raise
            warn(
                f"stored workflow {workflow_id} for slot {slot!r} no longer exists; "
                "creating a new workflow"
            )
            del state[slot]
            path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return client.save_workflow(slot, workflow, state_file=state_file)
