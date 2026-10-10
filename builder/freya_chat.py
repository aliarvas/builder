"""Bounded chat calls layered on the starter kit's unchanged Freya client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from . import freya


def _api(method: str, path: str, body: dict[str, Any] | None, timeout_seconds: float) -> Any:
    request = urllib.request.Request(
        freya.URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=freya.HEADERS,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            output = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"{method} {path} -> {exc.code}: {exc.read().decode()[:1500]}"
        ) from None
    if isinstance(output, dict):
        return output.get("data", {}).get("result", output)
    return output


def chat_message(
    workflow_id: str,
    message: str,
    customer_variables: dict[str, Any],
    call_id: str | None = None,
    timeout_seconds: float = 120,
) -> Any:
    """Run one chat turn against a published workflow."""
    body = {
        "workflowId": workflow_id,
        "message": message,
        "customerVariables": customer_variables,
    }
    if call_id:
        body["callId"] = call_id
    return _api("POST", "/api/v2/chat/message", body, timeout_seconds)


def get_call(call_id: str, timeout_seconds: float = 120) -> dict[str, Any]:
    """Read a self-test call record within the remaining test budget."""
    return _api("GET", f"/api/v2/call/{call_id}", None, timeout_seconds)["call"]


def end_chat(call_id: str, timeout_seconds: float = 120) -> Any:
    """End an unfinished self-test chat."""
    return _api("POST", "/api/v2/chat/end", {"callId": call_id}, timeout_seconds)
