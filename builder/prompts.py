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
        "Never say a payment or promise was recorded unless create_promise returned ok true. "
        "Never say a note or callback was recorded unless its tool returned ok true.\n"
        "If you have not yet given this introduction in this call, give it first in your next message, "
        "whatever the customer said: {introduction}\n"
        "Global rules:\n{rules}"
    ),
    runtime_placeholders=("{agent_name}", "{language}", "{introduction}", "{rules}"),
)

OPENING_TASK_TEMPLATE = PromptDefinition(
    "OPENING_TASK_TEMPLATE", "Opens the call and identifies who answered.", "phone agent",
    "builder/workflow.py — opening",
    "Start the call with this, once: {introduction}\nThe person to ask for is {address}. Use these words when you address them.\n"
    "Ask: {question}\n"
    "If they only greet you or check the line (for example \"Hello?\"), that is not an answer: reply briefly and ask the question again.\n"
    "If unclear: {unclear}\nBefore verification, do not say: {forbidden}\nRules:\n{rules}",
    ("{introduction}", "{address}", "{question}", "{unclear}", "{forbidden}", "{rules}"),
)
OPENING_REASK_TASK_TEMPLATE = PromptDefinition(
    "OPENING_REASK_TASK_TEMPLATE", "Asks the opening question again after an unclear answer, without a second introduction.",
    "phone agent", "builder/workflow.py — opening_reask",
    "You already gave the introduction earlier in this call. Do not repeat it unless they ask who is calling.\n"
    "The person to ask for is {address}. Use these words when you address them.\n"
    "Ask again, briefly: {question}\n"
    "If they only greet you or check the line, reply briefly and ask the question again.\n"
    "If unclear: {unclear}\nBefore verification, do not say: {forbidden}\nRules:\n{rules}",
    ("{address}", "{question}", "{unclear}", "{forbidden}", "{rules}"),
)
WHO_ANSWERED_DESCRIPTION = PromptDefinition(
    "WHO_ANSWERED_DESCRIPTION", "Extraction description of the who-answered variable in the opening steps.",
    "extraction model", "builder/workflow.py — opening and opening_reask extraction_schema",
    "Who answered the call. {greeting}: the person only greets or checks the line "
    "(for example \"Hello?\" or \"Who is this?\") and has not answered the question yet.",
    ("{greeting}",),
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
    "NEGOTIATION_TASK_TEMPLATE", "Discusses the account and obtains a date and an amount per product.", "phone agent",
    "builder/workflow.py — negotiate",
    "Today is {{today_text}}. Account facts, computed by the bank system:\n{{products_facts}}\n"
    "Use only these dates and amounts; never compute a deadline or a minimum yourself. "
    "Never read an internal id or the raw account result aloud; use the product type, customer-facing label, "
    "and list number. Refer to a product by its number when there are several.\n"
    "Last offer verdict: {{offer_verdict}}. Last offer check: {{offer_message}}\n"
    "Offers accepted so far: {{offers_summary}}\n"
    "If the last offer verdict is not ok, say the last offer check message before asking anything else. "
    "A checked or accepted offer is not recorded: never say a payment or promise was recorded here.\n"
    "Get a concrete date and amount from the customer. When the last offer check names a date or "
    "an amount, offer exactly that. If they cannot pay on one date, ask for another date; that alone is not "
    "a refusal.\nRules:\n{rules}",
    ("{rules}",),
)
OFFER_VERDICT_MESSAGES = PromptDefinition(
    "OFFER_VERDICT_MESSAGES", "One sentence per offer-check verdict, read by the agent in the negotiate step.",
    "phone agent (via offer_message)", "builder/offer_check.py — check_offer code step",
    "ok: The offer for product [product] is valid and noted.\n"
    "more: Now ask about the next product.\n"
    "missing: The date or the amount was not clear. Ask the customer for the exact date and amount.\n"
    "product_unknown: It is not clear which product the offer is for. Ask which product, by its number.\n"
    "date_too_early: That date is before the earliest allowed date. Offer [date] instead.\n"
    "date_too_late: That date is after the latest date that can be recorded for this product. Offer [date], the latest possible date.\n"
    "date_not_business_day: That date is not a business day. Offer [date], the next possible business day.\n"
    "date_ambiguous: Do you mean [date]?\n"
    "amount_too_low: That amount is below the minimum for this product. Offer [amount] instead.\n"
    "amount_too_high: That amount is more than the amount due. Offer [amount].",
)
CONFIRM_TASK_TEMPLATE = PromptDefinition(
    "CONFIRM_TASK_TEMPLATE", "Reads back and records a confirmed arrangement.", "phone agent",
    "builder/workflow.py — confirm_record",
    "Checked offers: {{offers_summary}}\nRead these back exactly and ask for a clear confirmation. "
    "After a clear yes, call the promise tool once per product, giving only its product number. "
    "Do not change a date or an amount yourself; if the customer wants a change, ask for the new value.\nRules:\n{rules}",
    ("{rules}",),
)
CLOSING_FALLBACK_SAY = PromptDefinition(
    "CLOSING_FALLBACK_SAY", "Spoken goodbye when the matched outcome row has an empty closing sentence.", "phone agent (fixed spoken line)",
    "builder/workflow.py — closing code step (closing_sentence)", "Thank you for your time. Goodbye.",
)
SPECIAL_PATH_TASK_TEMPLATE = PromptDefinition(
    "SPECIAL_PATH_TASK_TEMPLATE",
    "Handles a spec-defined special path whose tool needs a value only the conversation can give.",
    "phone agent", "builder/workflow.py — global special_<id> (model-filled tool only)",
    "The customer said: {when}\nCall the available tool once before claiming any action. "
    "Fill only the fields it asks for, from this call. "
    "Only if the tool result says ok true, say exactly: {say}\n"
    "If it did not return ok true, do not say anything was recorded or completed.",
    ("{when}", "{say}"),
)
SPECIAL_ASK_TASK_TEMPLATE = PromptDefinition(
    "SPECIAL_ASK_TASK_TEMPLATE", "Waits for the answer to a special path's first question.", "phone agent",
    "builder/workflow.py — global special_<id> with ask",
    "You asked: {ask}\nWait for the answer. Do not call any tool and do not promise anything.",
    ("{ask}",),
)

CONVERSATION_NO_TOOL_RULE = PromptDefinition(
    "CONVERSATION_NO_TOOL_RULE",
    "Explicitly forbids tool calls in a conversation step that exposes no tools.",
    "phone agent", "builder/workflow.py — every tool-free conversation task_message and loop_prompt",
    "Tool-use rule for this turn: No tool call is allowed in this turn.",
)
CONVERSATION_TOOL_RULE_TEMPLATE = PromptDefinition(
    "CONVERSATION_TOOL_RULE_TEMPLATE",
    "Names an exposed conversation tool exactly and states its call condition.",
    "phone agent", "builder/workflow.py — every tool-enabled conversation task_message and loop_prompt",
    "Tool-use rule for this turn: Call {tool_name} only when the customer's response meets this step's "
    "stated condition for that action and all required tool inputs are known; do not call it otherwise.",
    ("{tool_name}",),
)



# ---------------------------------------------------------------------------
# Builder-time extraction prompts (builder/extract.py). Receiver: the builder model.
# Generic: they describe the spec fields and the collections domain, never a brief.
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = PromptDefinition(
    "EXTRACTION_SYSTEM_PROMPT",
    "Sets the builder model's job: turn a bank collections brief into spec data with sources.",
    "builder model", "builder/extract.py — system prompt of every extraction call",
    "You turn a bank's collections brief into structured data for an outbound phone agent. "
    "A program builds the agent from your data, so every value must be exact.\n"
    "- Use only the documents given. Never invent a rule, value, outcome, reason, queue, date or sentence. "
    "If the documents give no value for a field, follow the field's fallback instruction and say so in sources.\n"
    "- The documents come in order. A later document, memo or correction overrides an earlier one: "
    "use only the newer value and list the change in overrides.\n"
    "- Every rule has a source: a short verbatim excerpt (at most 25 words) copied from the documents, "
    "so a reader can find it with a text search.\n"
    "- Do no arithmetic. Store counts, units and conditions as data; code computes dates and amounts.\n"
    "- Codes and enum values are copied exactly as written (same spelling and case). Tool field names come "
    "only from the tool contract.\n"
    "- Rule texts are short instructions to the phone agent, in English, one idea each. "
    "Sentences the agent must say word for word are copied exactly.\n"
    "- Reply with one JSON object only: no prose, no code fence.",
)

EXTRACTION_CONTEXT_TEMPLATE = PromptDefinition(
    "EXTRACTION_CONTEXT_TEMPLATE",
    "Shared first message of every extraction call: the documents, the tool contract and the call variables.",
    "builder model", "builder/extract.py — shared, cached context block",
    "# DOCUMENTS (in order; later overrides earlier)\n\n{documents}\n\n"
    "# TOOL CONTRACT (from the OpenAPI file)\n\n{contract}\n\n"
    "# CALL VARIABLES (known when the call starts)\n\n{call_variables}\n\n"
    "# PHONE AGENT SKELETON\n\n"
    "The program builds these steps; your data fills them: opening (introduction, find out who answered) -> "
    "third_party (someone else answered) or identity (security questions with the identity tool) -> "
    "account (fetch the late products) -> negotiate (get a date and an amount per product; code checks each "
    "offer against the date and amount rules) -> confirm_record (read back, confirm, record each promise) -> "
    "closing (one goodbye sentence, then the closing tool once). Special paths (for example a transfer "
    "request) can interrupt the steps they are available in. The closing outcome comes from a table that maps "
    "call-end states to outcome rows.",
    ("{documents}", "{contract}", "{call_variables}"),
)

_RULE_SHAPE = '{"text": "...", "source": "verbatim excerpt"}'

EXTRACT_OPENING_IDENTITY_TASK = PromptDefinition(
    "EXTRACT_OPENING_IDENTITY_TASK",
    "Extracts the agent identity, opening, third-party handling, identity check and global rules.",
    "builder model", "builder/extract.py — extraction call 'opening_identity'",
    "Extract the sections agent, opening, third_party, identity and global_rules. RULE means " + _RULE_SHAPE + ".\n"
    "Return this JSON shape:\n"
    "{\n"
    ' "agent": {"name": "how the agent presents itself", "language": "language of the call", '
    '"introduction": RULE (what the first sentence must say: who is calling, for whom, recording notice)},\n'
    ' "opening": {\n'
    '  "rules": [RULE] (other opening rules: what may be said before verification, how to answer questions '
    'about who or what is calling),\n'
    '  "confirmation_question": RULE (how to ask whether the intended customer is speaking),\n'
    '  "unclear_instruction": RULE (what to do when the answer does not confirm it),\n'
    '  "forbidden_before_verification": ["word or topic that must not be said before identity is verified"],\n'
    '  "address_with": ["call variable names used to address the customer, in spoken order"],\n'
    '  "max_unclear_asks": integer (how many times in total the confirmation question is asked, first ask '
    "included, before the call closes as unclear),\n"
    '  "answers": [{"value": "snake_case code", "meaning": "...", "route": "verify | other_person | ask_again | end", '
    '"outcome": "...", "reason": "...", "source": "..."}]\n'
    "   (every kind of answer to the confirmation question. route verify: the customer confirmed, go to the identity "
    "check. other_person: someone else answered. ask_again: unclear, ask again. end: the call closes right away; "
    "outcome and reason are the closing-table values for it, reason \"\" when the table has none. "
    "Exactly one value with route ask_again. Do not add a value for a bare greeting; the program adds it. "
    "Always include one value with route end for a person who refuses to talk or to confirm who they are; close "
    "it with the row the documents give for refusing before verification, or, if they name none, the closest row. "
    "If the documents do not name this case, its source is \"derived: <why this row>\" instead of an excerpt.)\n"
    " },\n"
    ' "third_party": {"rules": [RULE], "intents": [{"value": "snake_case code", "meaning": "...", '
    '"route": "stay | end", "outcome": "...", "reason": "...", "source": "..."}]}\n'
    "   (what the person who is not the customer may want. route end: the call closes with that outcome and reason, "
    "with no tool. A callback that is booked with a tool keeps route stay: the program closes it from the tool result.)\n"
    ' "identity": {\n'
    '  "rules": [RULE] (limits, refusal handling, what never to do before all questions pass),\n'
    '  "questions": [{"field": "value of the identity tool\'s question selector enum", "ask": RULE, '
    '"answer_format": RULE (how to convert the spoken answer into the tool format)}] (in the order asked),\n'
    '  "verified_field": "identity tool response field (boolean) that is true when the whole check passed",\n'
    '  "attempts_left_field": "identity tool response field (integer) with the wrong answers or attempts left",\n'
    '  "answer_verified_field": "identity tool response field (boolean) for the answer just checked",\n'
    '  "failed_answer_instruction": RULE (what to do after a failed answer, including any hint the tool returns),\n'
    '  "exhausted_say": RULE (what to tell the customer when no attempts are left)\n'
    " },\n"
    ' "global_rules": [RULE] (rules for the whole call: honesty, questions the agent cannot answer, '
    "repeated refusals to talk, recording claims, goodbye before the closing tool),\n"
    ' "sources": {"opening.max_unclear_asks": "excerpt or fallback: why", '
    '"opening.forbidden_before_verification": "excerpt"},\n'
    ' "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]\n'
    "}",
)

EXTRACT_FLOW_TASK = PromptDefinition(
    "EXTRACT_FLOW_TASK",
    "Extracts the account, negotiation and confirmation sections.",
    "builder model", "builder/extract.py — extraction call 'flow'",
    "Extract the sections account, negotiation and confirmation. RULE means " + _RULE_SHAPE + ".\n"
    "Date limits, amount limits and the offer limit are extracted elsewhere; here keep only the conversation rules.\n"
    "Return this JSON shape:\n"
    "{\n"
    ' "account": {"rules": [RULE] (how to state the debt and the products, in which order), '
    '"products_field": "account tool response field (array) with the late products", '
    '"product_id_field": "field of one product item that identifies it for the promise tool"},\n'
    ' "negotiation": {"rules": [RULE] (what to ask first, what counts as a refusal, persuasion attempts and what each '
    "proposes, what never to offer, per-product handling),\n"
    '  "intents": [{"value": "snake_case code", "meaning": "...", "route": "readback | end | stay", '
    '"outcome": "...", "reason": "...", "source": "..."}]\n'
    "   (the customer's state after each turn. route readback: an agreed date and amount are ready to read back. "
    "end: the customer refuses any arrangement after the allowed attempts; give the closing-table outcome and reason. "
    "stay: keep negotiating. At least one readback and one end value. Only refusing to pay or to talk may use "
    "route end. Situations with their own sentence or tool (the payment was already made, the debt is denied, "
    "a transfer is requested, financial difficulty) are special paths, extracted elsewhere: never list them here, or the call would close without "
    "the sentence or the tool.)},\n"
    ' "confirmation": {"rules": [RULE] (read-back, explicit confirmation, changes, one promise per product, '
    "what to say after a recorded promise, what to do when recording fails),\n"
    '  "promise_product_id_field": "promise tool request field for the product id",\n'
    '  "promise_date_field": "promise tool request field for the date",\n'
    '  "promise_amount_field": "promise tool request field for the amount",\n'
    '  "max_attempts_per_product": integer (recording attempts per product, the first one included),\n'
    '  "intents": [{"value": "snake_case code", "meaning": "...", "route": "record | change"}]\n'
    "   (record: the customer clearly confirmed the read-back. change: the customer wants a different date or amount, "
    "or rejects the read-back.)},\n"
    ' "sources": {"confirmation.max_attempts_per_product": "excerpt or fallback: why"},\n'
    ' "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]\n'
    "}",
)

EXTRACT_OFFER_TASK = PromptDefinition(
    "EXTRACT_OFFER_TASK",
    "Extracts the date and amount rules that code uses to check every offer.",
    "builder model", "builder/extract.py — extraction call 'offer'",
    "Extract the section offer: the calendar, the date limits and the amount limits a promise must meet. "
    "Code evaluates them against the call's current date; you only copy the rule data. RULE means " + _RULE_SHAPE + ".\n"
    "Return this JSON shape:\n"
    "{\n"
    ' "offer": {\n'
    '  "rules": [RULE] (date and amount rules the agent must also follow in conversation: vague periods, '
    "this/next weekday meaning, what to propose when a date or amount is not allowed),\n"
    '  "today_variable": "call variable with the current date and time",\n'
    '  "non_business_weekdays": [ISO weekday numbers, 1 = Monday ... 7 = Sunday],\n'
    '  "holidays": ["YYYY-MM-DD", every non-business date listed],\n'
    '  "promise_date_must_be_business_day": true or false,\n'
    '  "earliest": {"days": integer, "unit": "business | calendar"} (first allowed promise date counted from today; '
    "0 calendar days means today),\n"
    '  "latest": [{"when": [CONDITION], "days": integer, "unit": "business | calendar"}] (the latest allowed date, '
    "counted from today; ordered, the first rule whose conditions match the product applies; omit when for a rule "
    "that applies to every product),\n"
    '  "latest_on_non_business_day": "previous | next | keep" (when a calendar-day latest date is not a business day),\n'
    '  "min_amount": [{"when": [CONDITION], "field": "product field"} or {"when": [CONDITION], "value": number}, '
    'optional "share": fraction of the field or value],\n'
    '  "max_amount": [same shape as min_amount],\n'
    '  "next_weekday": "following_week | upcoming | ask" (what "next <weekday>" means. following_week: that weekday '
    "in the following calendar week. upcoming: the nearest such weekday after today. Use one of these two only if "
    "the documents define \"next <weekday>\"; otherwise ask, and the agent asks which date is meant),\n"
    '  "max_rejected_offers": integer, at least 2 (an invalid-offer counter: how many distinct customer offers that '
    "fail the date or amount checks above a product may have before it is given up. It is NOT the number of "
    "persuasion attempts after a refusal: never copy a persuasion or attempt count here. Use 2 (one invalid offer, "
    "then the agent's counter-offer may be rejected once) unless the documents set a limit on invalid or "
    "out-of-policy offers; give the source \"fallback: no invalid-offer limit in the documents\"),\n"
    '  "max_rejected_offers_by_product": [{"when": [CONDITION], "value": integer, at least 2}] (only if the documents '
    "set different invalid-offer limits for different products; otherwise []. Persuasion attempts per band are "
    "not invalid-offer limits)\n"
    " },\n"
    " CONDITION is {\"field\": \"product field\", and one or more of \"min\": number, \"max\": number, "
    "\"equals\": value, \"in\": [values]} (min and max are inclusive). Product fields come from the account tool's "
    "product items in the tool contract.\n"
    ' "sources": {"offer.<field>": "excerpt or fallback: why", one entry per field above},\n'
    ' "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]\n'
    "}",
)

EXTRACT_OUTCOMES_TASK = PromptDefinition(
    "EXTRACT_OUTCOMES_TASK",
    "Extracts the closing table, the special paths and the closing tool fields.",
    "builder model", "builder/extract.py — extraction call 'outcomes'",
    "Extract the sections outcomes, special_paths and closing. RULE means " + _RULE_SHAPE + ".\n"
    "Return this JSON shape:\n"
    "{\n"
    ' "closing": {"rules": [RULE], "outcome_field": "closing tool request field for the outcome", '
    '"reason_field": "closing tool request field for the reason"},\n'
    ' "outcomes": [{"outcome": "...", "reason": "... or \\"\\"", "when": RULE, "say": RULE (the goodbye sentence '
    "said before the closing tool; include every sentence the brief requires in that situation), "
    '"wins_over_promise": true or false (true only if this row is used even after a promise was recorded), '
    '"states": ["call-end state names below that close with this row"]}]\n'
    "   (one row per outcome and reason pair the brief allows; every pair from the closing table.)\n"
    ' "special_paths": [{"id": "snake_case", "when": RULE (what the customer says), "say": RULE (said word for word), '
    '"ask": RULE (optional; leave the key out unless the documents require one question before acting, for example '
    "whether the agent can help first or whether the customer wants to be connected. The agent says it to the customer "
    'and waits for the answer, so it must be one question ending with "?", never an instruction), '
    '"tool": "tool name or \\"\\"", "tool_args": {"field": "fixed value"}, "outcome": "...", "reason": "...", '
    '"available_in": ["opening | third_party | identity | negotiate | confirm_record"], "then": "close | return"}]\n'
    "   (situations that interrupt the normal flow, for example: the customer says the payment was already made, "
    "denies the debt, reports financial difficulty, asks for a different plan or for a person; or a note on one "
    "product. tool_args holds only values the brief fixes; fields the conversation must fill are "
    "left out. then close: the call closes with outcome and reason, which must be a row above. then return: the "
    "agent goes back to the step it came from (outcome and reason are still required; repeat a row's values). "
    "Do not use the identity, account, promise or closing tools here. available_in lists only steps where the "
    "situation may happen: never before identity is verified if it would disclose the account.)\n"
    ' "derived_states": {"state name": "why this row"} (every state below that the documents do not name, with '
    "the reason you chose its row; no excerpt needed),\n"
    ' "sources": {},\n'
    ' "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]\n'
    "}\n"
    "Code checks this reply; each failed check costs a repair round:\n"
    "- Every RULE (when, say, ask) has non-empty text and a source copied word for word from the documents; never "
    "\"derived\" or \"fallback\" in a rule source.\n"
    "- Each outcome and reason pair is written together in one row or sentence of the documents, copied exactly; "
    "reason is \"\" only when the documents give none. No pair appears twice.\n"
    "- Every special path's outcome and reason is one of the rows, also for then return.\n"
    "- tool_args keys are request fields of that tool; enum fields use an enum value from the tool contract.\n"
    "- Every state name below appears in exactly one row's states; every required state is mapped.\n"
    "- An ask is one question ending with \"?\" and only with then close; otherwise leave the key out.\n"
    "Call-end states. Map each required state to exactly one row. If the documents do not name a state, map it to "
    "the closest row and list it in derived_states. An optional state left out uses the row of \"default\":\n{states}",
    ("{states}",),
)

CLOSE_STATE_GUIDE = PromptDefinition(
    "CLOSE_STATE_GUIDE",
    "Meaning of each fixed call-end state, listed in the outcomes extraction call.",
    "builder model", "builder/extract.py — {states} in EXTRACT_OUTCOMES_TASK",
    "- opening_unclear (required): who answered stayed unclear after the allowed asks.\n"
    "- callback_scheduled (required): the callback tool booked a callback.\n"
    "- callback_failed: a callback could not be booked.\n"
    "- identity_failed (required): no identity attempts are left.\n"
    "- promise_recorded (required): at least one promise was recorded.\n"
    "- promise_failed (required): recording a promise failed on every allowed attempt.\n"
    "- account_failed (required): the account could not be fetched (a technical failure).\n"
    "- offer_limit (required): a product's offers kept failing the date and amount checks; usually the refusal row.\n"
    "- turn_limit: the conversation ran too long without progress.\n"
    "- special_tool_failed: a special path's tool failed.\n"
    "- hangup (required): the verified customer ended the call before the closing step.\n"
    "- hangup_unverified (required): the call ended before identity was verified.\n"
    "- default (required): the call ends in a way no other state covers, usually no promise.\n"
    "Route values that end the call (opening answers, third-party intents, negotiation intents with route end) "
    "are mapped through their own outcome and reason; do not list them here.",
)

EXTRACT_REPAIR_TEMPLATE = PromptDefinition(
    "EXTRACT_REPAIR_TEMPLATE",
    "Sends code-validation errors back for one extraction call.",
    "builder model", "builder/extract.py — repair round (same conversation)",
    "Code validation found these problems in your JSON:\n{errors}\n"
    "Fix them using the documents. Change nothing else. Return the complete corrected JSON object, same shape.",
    ("{errors}",),
)

COVERAGE_TASK_TEMPLATE = PromptDefinition(
    "COVERAGE_TASK_TEMPLATE",
    "Maps every brief item to the spec path that covers it, or marks it not relevant or missing.",
    "builder model", "builder/extract.py — coverage call",
    "Below are the numbered items of the documents and the extracted spec. For every item decide:\n"
    "- covered: the spec carries its meaning. Give the spec paths, for example \"opening.rules[0]\", "
    "\"offer.holidays\" or \"special_paths[2]\".\n"
    "- not_relevant: it gives no instruction to the phone agent (titles, background, examples already covered, "
    "notes about other documents).\n"
    "- missing: it is an instruction or value the phone agent needs and no spec path carries it.\n"
    "Return {\"items\": [{\"id\": number, \"status\": \"covered | not_relevant | missing\", \"paths\": [\"...\"]}]} "
    "with every item id exactly once.\n\n"
    "# ITEMS\n{items}\n\n# SPEC\n{spec}",
    ("{items}", "{spec}"),
)

COVERAGE_FOLLOWUP_TEMPLATE = PromptDefinition(
    "COVERAGE_FOLLOWUP_TEMPLATE",
    "Asks once for spec additions that cover the items the coverage call found missing.",
    "builder model", "builder/extract.py — targeted coverage re-ask",
    "These document items are not covered by the spec below:\n{items}\n\n"
    "For each item, either add it to the spec or explain why the phone agent does not need it. "
    "Return {\"additions\": [{\"items\": [ids], \"target\": \"<stage>.rules | global_rules | special_paths | outcomes\", "
    "\"value\": RULE or a full special path or outcome row in the spec's shape}], "
    "\"not_relevant\": [{\"item\": id, \"why\": \"...\"}]}. Stages: opening, third_party, identity, account, "
    "negotiation, confirmation, offer, closing. RULE means " + _RULE_SHAPE + ". "
    "Prefer a short rule in the step where it applies; use global_rules only for whole-call rules.\n\n# SPEC\n{spec}",
    ("{items}", "{spec}"),
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
    OPENING_REASK_TASK_TEMPLATE,
    WHO_ANSWERED_DESCRIPTION,
    THIRD_PARTY_TASK_TEMPLATE,
    IDENTITY_TASK_TEMPLATE,
    NEGOTIATION_TASK_TEMPLATE,
    OFFER_VERDICT_MESSAGES,
    CONFIRM_TASK_TEMPLATE,
    CLOSING_FALLBACK_SAY,
    SPECIAL_PATH_TASK_TEMPLATE,
    SPECIAL_ASK_TASK_TEMPLATE,
    CONVERSATION_NO_TOOL_RULE,
    CONVERSATION_TOOL_RULE_TEMPLATE,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_CONTEXT_TEMPLATE,
    EXTRACT_OPENING_IDENTITY_TASK,
    EXTRACT_FLOW_TASK,
    EXTRACT_OFFER_TASK,
    EXTRACT_OUTCOMES_TASK,
    CLOSE_STATE_GUIDE,
    EXTRACT_REPAIR_TEMPLATE,
    COVERAGE_TASK_TEMPLATE,
    COVERAGE_FOLLOWUP_TEMPLATE,
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
