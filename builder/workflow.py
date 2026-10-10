"""Render the T-001 minimal Freya workflow."""

from __future__ import annotations

from typing import Any


def _closing_transition() -> dict[str, Any]:
    return {
        "target_node": "hang_up",
        "description": "close_call succeeded",
        "condition": {
            "logic": "or",
            "conditions": [
                {
                    "variable": "close_call_response.data.ok",
                    "operator": "equals",
                    "operand": value,
                }
                for value in ("true", "True")
            ],
        },
    }


def build_workflow(brief_text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a generic one-conversation-node workflow from runtime inputs."""
    tool_names = {tool.get("function", {}).get("name") for tool in tools}
    if "close_call" not in tool_names:
        raise ValueError("OpenAPI document must define the fixed close_call POST tool")

    task_message = (
        "You are on a phone call. Follow the supplied bank brief exactly.\n\n"
        "Call variables: customer_id={{customer_id}}, first_name={{first_name}}, "
        "last_name={{last_name}}, title={{title}}, now={{now}}.\n\n"
        "When a rule requires a tool, call that tool; saying an action happened is not enough. "
        "After every tool result, speak to the customer or call the next required tool.\n\n"
        "# BANK BRIEF\n\n"
        + brief_text
    )
    return {
        "initial_node": "call",
        "system_prompt": (
            "You are a bank's digital assistant on an outbound phone call. Speak English. "
            "Keep every turn concise and truthful."
        ),
        "nodes": {
            "call": {
                "name": "call",
                "node_type": "conversation",
                "task_message": task_message,
                "tools": tools,
                "max_node_turns": 60,
                "max_turn_transition": "hang_up",
                "transitions": [
                    _closing_transition(),
                    {
                        "target_node": "call",
                        "description": "Keep going",
                        "condition": {"operator": "always"},
                    },
                ],
            },
            "hang_up": {
                "name": "hang_up",
                "node_type": "end_call",
                "on_enter": {"type": "silent"},
                "disable_inactivity_monitor": True,
                "transitions": [],
                "terminal": {
                    "type": "function",
                    "function": {
                        "name": "hang_up",
                        "handler": "__function__:end_call",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message_mode": {"type": "string", "default": "none"}
                            },
                        },
                    },
                },
            },
        },
        "global_nodes": {},
        "test_variables": {
            "customer_id": "placeholder_customer",
            "first_name": "Test",
            "last_name": "Customer",
            "title": "Mx",
            "now": "2000-01-03T12:00",
        },
    }
