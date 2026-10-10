"""Prompt catalog and readable documentation generator.

Add every future phone-agent or builder-model prompt here, never inline elsewhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptDefinition:
    """One builder-owned prompt and its human-readable metadata."""

    name: str
    purpose: str
    receiver: str
    used_at: str
    text: str
    runtime_placeholders: tuple[str, ...] = ()
    over_budget: bool = False


PHONE_AGENT_SYSTEM_PROMPT = PromptDefinition(
    name="PHONE_AGENT_SYSTEM_PROMPT",
    purpose="Sets the phone agent's global identity, language, brevity, and honesty rules.",
    receiver="phone agent",
    used_at="builder/workflow.py — workflow-level system_prompt",
    text=(
        "You are a bank's digital assistant on an outbound phone call. Speak English. "
        "Keep every turn concise and truthful. Call at most one tool per message. "
        "After every tool result, speak to the customer or call the next required tool. "
        "Never claim an action succeeded unless the tool result says it succeeded."
    ),
)


PHONE_AGENT_TASK_MESSAGE_TEMPLATE = PromptDefinition(
    name="PHONE_AGENT_TASK_MESSAGE_TEMPLATE",
    purpose="Gives the phone agent its runtime brief, call variables, and tool-use instructions.",
    receiver="phone agent",
    used_at="builder/workflow.py — call node task_message",
    text=(
        "You are on a phone call. Follow the supplied bank brief exactly.\n\n"
        "Call variables: customer_id={{customer_id}}, first_name={{first_name}}, "
        "last_name={{last_name}}, title={{title}}, now={{now}}.\n\n"
        "When a rule requires a tool, call that tool; saying an action happened is not enough. "
        "Use every returned result field exactly; do not invent values.\n\n"
        "# BANK BRIEF\n\n"
        "{brief_text}"
    ),
    runtime_placeholders=("{brief_text}",),
    over_budget=True,
)

TOOL_RESULT_FAILURE_MESSAGE = PromptDefinition(
    name="TOOL_RESULT_FAILURE_MESSAGE",
    purpose="Tells the phone agent that a tool action was not carried out without overriding retry policy.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — generic API post-hook",
    text=(
        "The action was NOT carried out. Do not say it was done. Follow the brief's rule for a "
        "failed action (retry if the brief allows it, otherwise tell the customer plainly)."
    ),
)

TOOL_RESULT_FALSE_FIELDS_TEMPLATE = PromptDefinition(
    name="TOOL_RESULT_FALSE_FIELDS_TEMPLATE",
    purpose="Makes negative boolean result fields explicit after an otherwise successful API call.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — generic API post-hook",
    text=(
        "The action ran, but these result fields are false: {fields}. Treat each as NOT satisfied; "
        "do not proceed as if it passed. Read every field of the result before speaking."
    ),
    runtime_placeholders=("{fields}",),
)

TOOL_RESULT_UNCLEAR_MESSAGE = PromptDefinition(
    name="TOOL_RESULT_UNCLEAR_MESSAGE",
    purpose="Prevents success claims when a tool response does not clearly prove success.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — generic API post-hook",
    text=(
        "The result does not clearly show that the action succeeded. Check every result field and "
        "do not claim success unless the result clearly proves it. Do not invent values."
    ),
)

TOOL_RESULT_OK_MESSAGE = PromptDefinition(
    name="TOOL_RESULT_OK_MESSAGE",
    purpose="Directs the phone agent after a clearly successful tool result.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — generic API post-hook",
    text=(
        "The action ran and returned ok. Read the other result fields exactly, then speak to the "
        "customer or call the next required tool. Do not invent values."
    ),
)

TOOL_CALL_TRIGGER = PromptDefinition(
    name="TOOL_CALL_TRIGGER",
    purpose="Reminds the phone agent that describing an API action does not execute it.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — tool description",
    text="CALL this tool whenever the situation above applies; saying you did it is not enough.",
)

TOOL_FIELD_DETAILS_TEMPLATE = PromptDefinition(
    name="TOOL_FIELD_DETAILS_TEMPLATE",
    purpose="Introduces concise OpenAPI field constraints in a tool description.",
    receiver="phone agent",
    used_at="builder/tools_from_openapi.py — tool description",
    text="Fields: {field_details}",
    runtime_placeholders=("{field_details}",),
)

MULTI_STEP_SYSTEM_PROMPT_TEMPLATE = PromptDefinition(
    name="MULTI_STEP_SYSTEM_PROMPT_TEMPLATE",
    purpose="Sets spec-derived identity and global rules for the multi-step phone agent.",
    receiver="phone agent",
    used_at="builder/workflow.py — spec workflow system_prompt",
    text=(
        "You are {agent_name}. Speak {language}. Keep every turn concise and truthful. "
        "Call at most one tool per message. Never claim an action succeeded unless its tool result says so.\n"
        "Global rules:\n{rules}"
    ),
    runtime_placeholders=("{agent_name}", "{language}", "{rules}"),
)

OPENING_TASK_TEMPLATE = PromptDefinition(
    "OPENING_TASK_TEMPLATE", "Opens the call and identifies who answered.", "phone agent",
    "builder/workflow.py — opening",
    "Say: {introduction}\nThe person to ask for is {address}. Use these words when you address them.\n"
    "Ask: {question}\nIf unclear: {unclear}\nBefore verification, do not say: {forbidden}\nRules:\n{rules}",
    ("{introduction}", "{address}", "{question}", "{unclear}", "{forbidden}", "{rules}"),
)
THIRD_PARTY_TASK_TEMPLATE = PromptDefinition(
    "THIRD_PARTY_TASK_TEMPLATE", "Handles a person other than the customer.", "phone agent",
    "builder/workflow.py — third_party", "Handle the third-party response without disclosing protected details.\nRules:\n{rules}",
    ("{rules}",),
)
IDENTITY_TASK_TEMPLATE = PromptDefinition(
    "IDENTITY_TASK_TEMPLATE", "Asks ordered identity questions and uses the verification tool.", "phone agent",
    "builder/workflow.py — identity",
    "Ask these security questions one at a time, in order. Call the identity tool with each answer:\n{questions}\n"
    "Convert the customer's spoken answer into the tool format yourself. Never ask the customer to say a technical format.\n"
    "After each tool result:\n"
    "- {answer_verified} is true: acknowledge briefly and ask the next question. "
    "After the last question, ask nothing more; say the answers matched and give no account details yet.\n"
    "- {answer_verified} is false: say the answer did not match. Do not thank them as if it passed. "
    "Ask the same question again; never move to the next question until this one is verified. {failed_answer}\n"
    "- The action was not carried out: ask for the same answer again; it is not a wrong answer.\n"
    "- {attempts_left} is 0: {exhausted_say} Ask nothing more and give no account details.\n"
    "Rules:\n{rules}",
    ("{questions}", "{answer_verified}", "{failed_answer}", "{attempts_left}", "{exhausted_say}", "{rules}"),
)
NEGOTIATION_TASK_TEMPLATE = PromptDefinition(
    "NEGOTIATION_TASK_TEMPLATE", "Discusses the account and obtains an arrangement proposal.", "phone agent",
    "builder/workflow.py — negotiate", "Discuss only the account information already retrieved.\nRules:\n{rules}",
    ("{rules}",),
)
CONFIRM_TASK_TEMPLATE = PromptDefinition(
    "CONFIRM_TASK_TEMPLATE", "Reads back and records a confirmed arrangement.", "phone agent",
    "builder/workflow.py — confirm_record", "Read the proposal back, obtain confirmation, then call the promise tool.\nRules:\n{rules}",
    ("{rules}",),
)
CLOSING_FALLBACK_SAY = PromptDefinition(
    "CLOSING_FALLBACK_SAY", "Spoken goodbye when the matched outcome row has an empty closing sentence.", "phone agent (fixed spoken line)",
    "builder/workflow.py — closing code step (closing_sentence)", "Thank you for your time. Goodbye.",
)
SPECIAL_PATH_TASK_TEMPLATE = PromptDefinition(
    "SPECIAL_PATH_TASK_TEMPLATE", "Handles one spec-defined exceptional customer path.", "phone agent",
    "builder/workflow.py — special_*", "Condition: {when}\nSay or do: {say}\nUse the available tool when required, then follow the configured route.",
    ("{when}", "{say}"),
)


PROMPTS = (
    PHONE_AGENT_SYSTEM_PROMPT,
    PHONE_AGENT_TASK_MESSAGE_TEMPLATE,
    TOOL_RESULT_FAILURE_MESSAGE,
    TOOL_RESULT_FALSE_FIELDS_TEMPLATE,
    TOOL_RESULT_UNCLEAR_MESSAGE,
    TOOL_RESULT_OK_MESSAGE,
    TOOL_CALL_TRIGGER,
    TOOL_FIELD_DETAILS_TEMPLATE,
    MULTI_STEP_SYSTEM_PROMPT_TEMPLATE,
    OPENING_TASK_TEMPLATE,
    THIRD_PARTY_TASK_TEMPLATE,
    IDENTITY_TASK_TEMPLATE,
    NEGOTIATION_TASK_TEMPLATE,
    CONFIRM_TASK_TEMPLATE,
    CLOSING_FALLBACK_SAY,
    SPECIAL_PATH_TASK_TEMPLATE,
)


def render_phone_agent_system_prompt() -> str:
    return PHONE_AGENT_SYSTEM_PROMPT.text


def render_phone_agent_task_message(brief_text: str) -> str:
    return PHONE_AGENT_TASK_MESSAGE_TEMPLATE.text.replace("{brief_text}", brief_text)


def render_prompt(prompt: PromptDefinition, **values: str) -> str:
    """Render known catalog placeholders without interpreting Freya ``{{variables}}``."""
    text = prompt.text
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def generate_prompt_doc() -> str:
    """Render the deterministic Markdown mirror of every prompt."""
    lines = [
        "# Prompts",
        "",
        "Generated from `builder/prompts.py`. Do not edit by hand; edit the code and regenerate.",
        "",
    ]
    for prompt in PROMPTS:
        static_text = prompt.text
        for placeholder in prompt.runtime_placeholders:
            static_text = static_text.replace(placeholder, "")
        static_tokens = math.ceil(len(static_text) / 4)
        if prompt.runtime_placeholders:
            runtime_terms = " + ".join(
                f"`{placeholder}` characters ÷ 4" for placeholder in prompt.runtime_placeholders
            )
            token_estimate = f"~{static_tokens} static + {runtime_terms} at runtime"
        else:
            token_estimate = f"~{static_tokens} (characters ÷ 4)"
        lines.extend(
            [
                f"## {prompt.name}",
                "",
                f"- Purpose: {prompt.purpose}",
                f"- Receiver: {prompt.receiver}",
                f"- Used at: {prompt.used_at}",
                f"- Approximate tokens: {token_estimate}",
                *(
                    [
                        "- Budget: **OVER BUDGET** — the complete runtime brief is inserted and can exceed 1,500 tokens."
                    ]
                    if prompt.over_budget
                    else []
                ),
                "",
                "```text",
                prompt.text,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def prompt_doc_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "PROMPTS.md"


def main() -> int:
    path = prompt_doc_path()
    path.write_text(generate_prompt_doc(), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
