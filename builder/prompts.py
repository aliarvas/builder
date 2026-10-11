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
        "Call at most one tool per message. Never claim an action succeeded unless its tool returned ok true. "
        "Use the word \"recorded\" only for an action whose tool returned ok true in this call (a payment or promise: "
        "create_promise); for the recording notice say \"we are recording this call\".\n"
        "Global rules:\n{rules}"
    ),
    runtime_placeholders=("{agent_name}", "{language}", "{rules}"),
)

OPENING_TASK_TEMPLATE = PromptDefinition(
    "OPENING_TASK_TEMPLATE", "Opens the call and identifies who answered.", "phone agent",
    "builder/workflow.py — opening",
    "Your first words in this call, whatever the customer said, and only once: {introduction}\n"
    "If you already gave the introduction in this call, do not repeat it: answer briefly and ask the question again.\nThe person to ask for is {address}. Use these words when you address them.\n"
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
    "WHO_ANSWERED_DESCRIPTION", "Extraction description of the who-answered variable in the opening steps; "
    "every value is described (F-071). A line whose value list is empty is left out.",
    "extraction model", "builder/workflow.py — opening and opening_reask extraction_schema",
    "Who answered the call.\n"
    "{confirm}: the person clearly confirms they are the customer. The documents' rule: {unclear_rule}\n"
    "{other}: only when the person clearly says they are not the customer (for example someone else's name, "
    "\"she is not here\", \"I am his wife\").\n"
    "{close}: only when the person clearly says what that value names.\n"
    "{stay}: anything else that does not confirm, including a garbled or half-heard answer, an answer in "
    "another language, or a question back.\n"
    "{greeting}: the person only greets or checks the line (for example \"Hello?\" or \"Who is this?\") and "
    "has not answered the question yet.",
    ("{confirm}", "{unclear_rule}", "{other}", "{close}", "{stay}", "{greeting}"),
)
THIRD_PARTY_TASK_TEMPLATE = PromptDefinition(
    "THIRD_PARTY_TASK_TEMPLATE", "Handles a person other than the customer.", "phone agent",
    "builder/workflow.py — third_party", "Handle the third-party response without disclosing protected details.\nRules:\n{rules}",
    ("{rules}",),
)
THIRD_PARTY_INTENT_DESCRIPTION = PromptDefinition(
    "THIRD_PARTY_INTENT_DESCRIPTION",
    "Restricts third-party closing intents to situations named by the spec's closing values (F-064).",
    "extraction model", "builder/callback.py — third_party intent extraction field",
    "The third party's current intent. Closing values are: {close_values}. Choose one when the person's message "
    "clearly states the situation that value names. A question, an offer to pay, or a request for account or "
    "payment information is not a closing situation: choose none so the agent can decline to disclose details "
    "and ask when the customer can be reached.",
    ("{close_values}",),
)
THIRD_PARTY_CUSTOMER_DESCRIPTION = PromptDefinition(
    "THIRD_PARTY_CUSTOMER_DESCRIPTION",
    "Adds the framework value for a third party who is in fact the customer (F-069).",
    "extraction model", "builder/workflow.py — appended to the third_party intent extraction field",
    "{value}: the person says they are the customer themselves, or the customer has come to the phone.",
    ("{value}",),
)
NO_SECURITY_QUESTIONS_LINE = PromptDefinition(
    "NO_SECURITY_QUESTIONS_LINE",
    "Keeps security questions out of the steps before identity verification (F-070).",
    "phone agent", "builder/workflow.py — opening, opening_reask, third_party and third_party_ask task_message",
    "Never ask security questions or for personal data in this step; only the program verifies identity, later.",
)
NO_GOODBYE_LINE = PromptDefinition(
    "NO_GOODBYE_LINE",
    "Keeps the goodbye in the closing step (F-072).",
    "phone agent", "builder/workflow.py — every conversation task_message except the step that says the closing sentence",
    "Never say goodbye or end the call yourself; the program closes the call.",
)
SIDE_QUESTION_LINE = PromptDefinition(
    "SIDE_QUESTION_LINE",
    "A side question asked in the same turn as a business answer is not lost (F-074).",
    "phone agent", "builder/workflow.py — conversation steps where a spoken-only returning special path may fire, or that speak right after one; followed by one SIDE_QUESTION_ITEM per path",
    "If the customer asked one of these and has no answer yet, first say its answer, then go on:",
)
SIDE_QUESTION_ITEM = PromptDefinition(
    "SIDE_QUESTION_ITEM",
    "One spoken-only returning special path under SIDE_QUESTION_LINE (F-074).",
    "phone agent", "builder/workflow.py — one line per path: its when text and its fixed answer",
    "- {when} Say: \"{say}\"",
)
THIRD_PARTY_CLOSE_KIND_DESCRIPTION = PromptDefinition(
    "THIRD_PARTY_CLOSE_KIND_DESCRIPTION",
    "Provides an independent guard signal for third-party closing intents (F-064).",
    "extraction model", "builder/callback.py — third_party close-kind extraction field",
    "Classify only the third party's last message. Closing values are: {close_values}. Choose explicit_close when "
    "the person clearly states a situation named by one of those values, for example a refusal of a callback, "
    "that the customer cannot be reached, or \"she doesn't want to be called\". Choose other for every question, "
    "offer to pay, request for information, vague reply, or non-answer, for example \"I can pay it myself if you "
    "tell me the amount\".",
    ("{close_values}",),
)
IDENTITY_TASK_TEMPLATE = PromptDefinition(
    "IDENTITY_TASK_TEMPLATE", "Asks ordered identity questions and uses the verification tool.", "phone agent",
    "builder/workflow.py — identity",
    "Ask these security questions one at a time, in order. Call the identity tool with each answer:\n{questions}\n"
    "Convert the customer's spoken answer into the tool format yourself. Never ask the customer to say a technical format.\n"
    "After each tool result:\n"
    "- {answer_verified} is true: acknowledge briefly and ask the next question. "
    "After the last question, ask nothing more; say the answers matched, then say: {wait_line} Give no account details yet.\n"
    "- {answer_verified} is false: say the answer did not match. Do not thank them as if it passed. "
    "Ask the same question again; never move to the next question until this one is verified. {failed_answer}\n"
    "- The action was not carried out: ask for the same answer again; it is not a wrong answer.\n"
    "- {attempts_left} is 0: {exhausted_say} Ask nothing more and give no account details.\n"
    "Rules:\n{rules}",
    ("{questions}", "{answer_verified}", "{failed_answer}", "{wait_line}", "{attempts_left}", "{exhausted_say}", "{rules}"),
)
NEGOTIATION_TASK_TEMPLATE = PromptDefinition(
    "NEGOTIATION_TASK_TEMPLATE", "Discusses the account and obtains a date and an amount per product.", "phone agent",
    "builder/workflow.py — negotiate",
    "Calendar: {{calendar_text}}\nAccount facts: {{products_facts}}\n"
    "Last offer verdict: {{offer_verdict}}. Last offer check: {{offer_message}}\n"
    "Offers accepted so far: {{offers_summary}}\n"
    "Use only these dates and amounts; never work out a date or an amount yourself. Name each product as the "
    "account facts do, "
    "never by a list number. Never read an internal id aloud. Never mention internal step, tool or variable "
    "names, and never write code.\n"
    "The bank system checks every date and amount the customer names and has already said the last offer check to "
    "the customer: do not repeat it; answer the customer, offering exactly a date or an amount it names. "
    "Verdict none: propose or ask, but never say whether a date or an amount is allowed. Never state a limit "
    "yourself unless the last offer check names it.\n"
    "A checked offer is not recorded: never say a payment or promise was recorded.\n"
    "Get a concrete date and amount. If the customer names only a date, the amount you last proposed applies. "
    "Not paying on one date is not a refusal: ask for another date.\nRules:\n{rules}",
    ("{rules}",),
)
OFFER_VERDICT_MESSAGES = PromptDefinition(
    "OFFER_VERDICT_MESSAGES", "One customer-facing sentence per offer-check verdict, spoken word for word after the check.",
    "customer (fixed spoken line via offer_message)", "builder/offer_check.py — check_offer; builder/workflow.py — offer_say",
    # F-053: spoken word for word to the customer by a fixed line after the check.
    "ok: Thank you, that works for the [product].\n"
    "more: Now let us look at the [next]. The amount due is [next_amount]. Could you pay [next_amount]?\n"
    "missing: Could you tell me the exact day you would like to pay?\n"
    # T-022 (F-076): no readable date; the code proposes the latest allowed date and keeps it.
    "missing_latest: Could you tell me the exact day you would like to pay? The latest date I can record for the [product] is [date]. Would [date] work for you?\n"
    "missing_again: Please tell me the day and the month, for example [date].\n"
    "amount_missing: Could you pay [amount]?\n"
    "product_unknown: Which of your products is this payment for?\n"
    "date_too_early: I can only record a date from [date]. Would [date] work for you?\n"
    "date_too_late: The latest date I can record for the [product] is [date]. Would [date] work for you?\n"
    "date_not_business_day: That day is not a business day. The next possible day is [date]. Would that work for you?\n"
    "date_ambiguous: Do you mean [date]?\n"
    "amount_too_low: The lowest amount I can record for the [product] is [amount]. Could you pay [amount]?\n"
    "amount_too_high: The amount due on the [product] is [amount]. Could you pay [amount]?",
)
OFFER_PRODUCT_NAME_DESCRIPTION = PromptDefinition(
    "OFFER_PRODUCT_NAME_DESCRIPTION",
    "Which product an offer is for, in the customer's words; the code matches it against the product names (T-025).",
    "extraction model", "builder/offer_check.py — negotiate extraction field offer_product_name (specs with several products)",
    "The product or products the customer's last message names for this payment, copied in the customer's words "
    "(for example the kind of product, the last digits, or \"both\"). Empty if the message names no product.",
)
OFFER_REFUSED_PRODUCTS_DESCRIPTION = PromptDefinition(
    "OFFER_REFUSED_PRODUCTS_DESCRIPTION",
    "The products the customer refuses in the same message, in their words; the code counts a refusal for each (T-027).",
    "extraction model",
    "builder/product_notes.py — negotiate extraction field offer_refused_product_name (specs with per-product refusals)",
    "The product or products the customer's last message refuses to pay, copied in the customer's words "
    "(for example the kind of product, the last digits, or \"the others\"). Empty unless this message itself "
    "refuses a product; never copy a product from an earlier message.",
)
READBACK_LINE = PromptDefinition(
    "READBACK_LINE", "Read-back the confirmation step says on entry, built by code from the checked offers "
    "(T-027, PUB-12: the model never read it back and the step waited for a confirmation forever).",
    "phone agent (fixed spoken line)", "builder/offer_check.py — readback_text, spoken by confirm_record",
    "I can record {payments}. Do you confirm?",
    ("{payments}",),
)
READBACK_ITEM = PromptDefinition(
    "READBACK_ITEM", "One checked offer in the read-back line (T-027).", "phone agent (fixed spoken line)",
    "builder/offer_check.py — readback_text",
    "a payment of {amount} for the {product} on {date}",
    ("{amount}", "{product}", "{date}"),
)
CONFIRM_READBACK_SAID_LINE = PromptDefinition(
    "CONFIRM_READBACK_SAID_LINE", "Tells the confirmation step that the program has already said the read-back (T-027).",
    "phone agent", "builder/goodbye.py — confirm_record",
    "The program has just said this read-back to the customer: \"{{readback_text}}\" Do not read it again unless "
    "the customer asks; answer the customer and wait for one clear confirmation.",
)
CUSTOMER_ENDS_CALL_INTENT = PromptDefinition(
    "CUSTOMER_ENDS_CALL_INTENT", "Routing intent of the global step for a customer who ends the call (T-027, "
    "PUB-12: \"Thank you, goodbye\" matched no route and the step repeated itself; T-029: every step).",
    "routing model", "builder/goodbye.py — global step customer_ends_call",
    "The customer clearly takes leave (goodbye, bye, or that they are done) and says nothing else: not an "
    "answer to a question, no refusal, no offer and no question. \"Thanks\", \"okay\" or \"yes\" alone is "
    "not a goodbye.",
)
GOODBYE_CHOICE_DESCRIPTION = PromptDefinition(
    "GOODBYE_CHOICE_DESCRIPTION", "Choice value of a global ask step for a customer who ends the call there; a "
    "global step cannot start the goodbye step (T-029).", "extraction model",
    "builder/goodbye.py — choice field of each global conversation step",
    " {value}: the customer only takes leave (goodbye, or that they are done) and gives no answer; \"thanks\", "
    "\"okay\" or \"yes\" alone is not {value}, and a \"no\" (also \"no thanks, goodbye\") answers the question.",
    ("{value}",),
)
CONFIRM_TASK_TEMPLATE = PromptDefinition(
    "CONFIRM_TASK_TEMPLATE", "Reads back the checked offers once and asks for one confirmation; the program "
    "records them (F-063).", "phone agent",
    "builder/workflow.py — confirm_record",
    "Checked offers: {{offers_summary}}\nRead all of these back once, in these words, and ask for one clear "
    "confirmation. Never say the product number in square brackets. "
    "After a clear yes, say nothing more: the program records the promises and the closing tells the customer. "
    "Never say a promise is recorded. "
    "Do not change a date or an amount yourself; if the customer wants a change, ask for the new value.\n"
    "You have no tool here: where a rule below speaks of calling, retrying or checking the promise tool, "
    "the program does that after the yes.\nRules:\n{rules}",
    ("{rules}",),
)
ACCOUNT_WAIT_LINE = PromptDefinition(
    "ACCOUNT_WAIT_LINE", "Line said after identity passed, before the account lookup, when the spec gives none (F-043, F-050).",
    "phone agent (in the identity step prompt)", "builder/workflow.py — identity step, {wait_line}",
    "Thank you. One moment while I check your account.",
)
REVISE_ASK_LINE = PromptDefinition(
    "REVISE_ASK_LINE", "Fixed line when the customer wants to change the read-back (F-053).",
    "phone agent (fixed spoken line)", "builder/workflow.py — revise_ask",
    "Of course. Which date or amount would you like instead?",
)
READBACK_RESUME_LINE = PromptDefinition(
    "READBACK_RESUME_LINE", "Fixed line when the call returns to the read-back after a side question; the "
    "read-back itself is not said again (T-032).", "phone agent (fixed spoken line)",
    "builder/readback_resume.py — confirm_record_resume",
    "Shall I go ahead with the payments I read out?",
)
PERSUASION_STATE_LINE = PromptDefinition(
    "PERSUASION_STATE_LINE", "Tells the negotiation step which persuasion attempt it is on (F-062) and what one "
    "persuasion turn may do (T-030, PUB-12: the model read back, said \"recorded\" and said goodbye).", "phone agent",
    "builder/product_notes.py — negotiate (only when the spec gives persuasion attempts)",
    "Persuasion attempts used on this product (bank count): {attempt}. Each turn: one reason the documents "
    "allow, then ask if and when they can pay; never read back or sum up offers, say \"record\" or \"confirm\", "
    "or thank them.",
    ("{attempt}",),
)
PERSUASION_PRODUCT_LINE = PromptDefinition(
    "PERSUASION_PRODUCT_LINE", "Names the product a counted persuasion attempt is about (T-027, PUB-12); the bank "
    "system moves to the next product (T-030).", "phone agent",
    "builder/product_notes.py — negotiate (specs with per-product refusals and persuasion attempts)",
    "Talk only about the {product}.",
    ("{product}",),
)
PRODUCT_INTENT_DESCRIPTION = PromptDefinition(
    "PRODUCT_INTENT_DESCRIPTION", "Extraction meaning of the per-product refusal values (F-062).", "extraction model",
    "builder/product_notes.py — negotiate extraction field",
    "Values {product_end} end only the product being discussed; the call goes on with the other products. "
    "Values {attempt} are a flat refusal or a non-answer about the product being discussed, which uses one "
    "persuasion attempt.",
    ("{product_end}", "{attempt}"),
)
PRODUCT_END_COUNTED_DESCRIPTION = PromptDefinition(
    "PRODUCT_END_COUNTED_DESCRIPTION",
    "Extraction note when the spec gives persuasion attempts: code decides when a product ends (AB-FRESH).",
    "extraction model", "builder/product_notes.py — negotiate extraction field (only with persuasion attempts)",
    "The bank system counts the persuasion attempts and ends the product only when they are used up; "
    "while attempts are left, {product_end} also uses one attempt. For any no about the product being "
    "discussed, choose {attempt}.",
    ("{product_end}", "{attempt}"),
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
SPECIAL_CLOSE_TOOL_TASK_TEMPLATE = PromptDefinition(
    "SPECIAL_CLOSE_TOOL_TASK_TEMPLATE",
    "Handles a special path that ends the call and whose tool needs a value only the conversation can give. "
    "The closing step speaks the path's line after the tool, so this step says nothing then (F-056 fix).",
    "phone agent", "builder/workflow.py — special_<id> (model-filled tool, then close)",
    "The customer said: {when}\nCall the available tool once. Fill only the fields it asks for, from this call. "
    "If a field is not known yet, ask only for it and call no tool.\n"
    "When you call the tool, say nothing before or after it: the next step speaks to the customer. "
    "Never say that anything was recorded or completed.",
    ("{when}",),
)
SPECIAL_SAY_FALLBACK = PromptDefinition(
    "SPECIAL_SAY_FALLBACK",
    "Spoken instead of a special path's line when the spec's line is an instruction to the agent (F-047).",
    "phone agent (fixed spoken line)", "builder/workflow.py — special path say fallback",
    "Thank you for letting me know.",
)
SPECIAL_TOOL_FAILED_SAY = PromptDefinition(
    "SPECIAL_TOOL_FAILED_SAY",
    "Said before the closing sentence when a closing special path's tool failed and the spec has no line "
    "for that state (F-059).",
    "phone agent (fixed spoken line)", "builder/workflow.py — closing code, special_tool_failed",
    "I am sorry, I could not complete that request right now.",
)
PROMISE_NOT_ALL_RECORDED_SAY = PromptDefinition(
    "PROMISE_NOT_ALL_RECORDED_SAY",
    "Said before the closing sentence when a promise could not be recorded and the outcome row is not the "
    "spec's own row for that (for example another promise was recorded) (F-063).",
    "phone agent (fixed spoken line)", "builder/workflow.py — closing code, promise_failed",
    "I am sorry, I could not record every promise.",
)
CALLBACK_COLLECT_RULE = PromptDefinition(
    "CALLBACK_COLLECT_RULE",
    "Added to the third-party step when the program books callbacks itself (F-055 review finding 3).",
    "phone agent", "builder/callback.py — third_party and third_party_ask task",
    "To arrange a callback, get the day and the time of day when the customer can be reached, in the person's "
    "own words; if they give only one of them, ask for the other. Never say a callback is booked or arranged: "
    "the program books it and the closing tells them.",
)
CALLBACK_DAY_DESCRIPTION = PromptDefinition(
    "CALLBACK_DAY_DESCRIPTION",
    "Extraction field in the third-party step: the person's words for the callback day (F-055).",
    "phone agent (extraction)", "builder/callback.py — third_party extraction callback_day_text",
    "Copy the words for the day when the customer can be called back from the person's last message, unchanged "
    "(for example \"tomorrow\", \"Friday\", \"the 15th\"). Do not resolve relative dates with the system clock. "
    "Empty if they name no day.",
)
CALLBACK_TIME_DESCRIPTION = PromptDefinition(
    "CALLBACK_TIME_DESCRIPTION",
    "Extraction field in the third-party step: the person's words for the callback time (F-055).",
    "phone agent (extraction)", "builder/callback.py — third_party extraction callback_time_text",
    "Copy the words for the time of day when the customer can be called back from the person's last message, "
    "unchanged, with any morning/afternoon/evening or am/pm words (for example \"around eleven in the morning\", "
    "\"3pm\", \"14:30\"). Empty if they name no time.",
)
CALLBACK_OUTSIDE_SAY = PromptDefinition(
    "CALLBACK_OUTSIDE_SAY",
    "Spoken when the callback time the person gave is outside the callback window (F-055); code fills {window}.",
    "phone agent (fixed spoken line)", "builder/callback.py — third_party_ask entry line",
    "I am sorry, we cannot call back then. We can call back {window}. What time would suit?",
    ("{window}",),
)
CALLBACK_UNCLEAR_SAY = PromptDefinition(
    "CALLBACK_UNCLEAR_SAY",
    "Spoken when the callback day or time could not be understood (F-055).",
    "phone agent (fixed spoken line)", "builder/callback.py — third_party_ask entry line",
    "Sorry, could you tell me the day and the time when we can call back?",
)
CALLBACK_TIME_ASK_SAY = PromptDefinition(
    "CALLBACK_TIME_ASK_SAY",
    "Spoken when the person named a callback day but no time; the day is kept for the next turn (F-055).",
    "phone agent (fixed spoken line)", "builder/callback.py — third_party_ask entry line",
    "Thank you. At what time of day can we call back?",
)
THIRD_PARTY_CLOSE_REASK_SAY = PromptDefinition(
    "THIRD_PARTY_CLOSE_REASK_SAY",
    "One bounded re-ask when a third-party closing intent lacks an explicit refusal (F-064).",
    "phone agent (fixed spoken line)", "builder/callback.py — third_party_ask entry line",
    "I cannot discuss account or payment details. When can the customer be reached?",
)
SPECIAL_ASK_PHRASED_TEMPLATE = PromptDefinition(
    "SPECIAL_ASK_PHRASED_TEMPLATE",
    "Lets the agent phrase a special path's question when the spec gives an instruction instead of words (F-047).",
    "phone agent", "builder/workflow.py — global special_<id> with ask (fallback)",
    "Ask the customer this as one short question, in your own words: {ask}\n"
    "Wait for the answer. Do not call any tool and do not promise anything.",
    ("{ask}",),
)
SPECIAL_SAY_FIRST_LINE = PromptDefinition(
    "SPECIAL_SAY_FIRST_LINE",
    "Puts a special path's line before its question when the spec says so (say_first, T-028, PUB-05: sympathy before the offer).",
    "phone agent", "builder/workflow.py — global special_<id> with ask and say_first",
    'Before the question, say word for word: "{say}"\n',
    ("{say}",),
)
SPECIAL_ASK_TASK_TEMPLATE = PromptDefinition(
    "SPECIAL_ASK_TASK_TEMPLATE", "Waits for the answer to a special path's first question.", "phone agent",
    "builder/workflow.py — global special_<id> with ask",
    "You asked: {ask}\nWait for the answer. Do not call any tool and do not promise anything.",
    ("{ask}",),
)
SPECIAL_CHOICE_DESCRIPTION = PromptDefinition(
    "SPECIAL_CHOICE_DESCRIPTION",
    "Reads the answer to a special path's question by what the customer wants done, not by yes or no (T-023, PUB-05).",
    "extraction model", "builder/workflow.py — choice field of a global special_<id> with ask",
    'The agent asked: "{ask}" proceed: the customer wants the agent to go ahead now and {action}. '
    "stay: the customer does not want that, or wants to go on with the call. "
    "Judge by what the customer wants done, not by the word yes or no.",
    ("{ask}", "{action}"),
)
SPECIAL_TOPIC_DESCRIPTION = PromptDefinition(
    "SPECIAL_TOPIC_DESCRIPTION",
    "Gives a step's choice field a value for a special situation, so the step's own routes leave the turn to the "
    "special paths (T-023, PUB-08).",
    "extraction model", "builder/workflow.py — appended to a step's choice field when special paths can start there",
    " {value}: the customer's message is about one of these: {situations}. Choose {value} instead of any other "
    "value, also a refusal, an agreement or unclear.",
    ("{value}", "{situations}"),
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
    "call-end states to outcome rows.\n\n"
    "# RULES THE PROGRAM ALREADY ENFORCES\n\n"
    "Any RULE may carry \"enforced_by\" when program code already guarantees exactly that rule. Such a rule can "
    "be left out of the phone agent's prompt to save room; it stays in the spec. Allowed values:\n"
    "- offer_dates: a promise date before the earliest or after the latest allowed date is rejected and the allowed "
    "date is offered; each product's deadline is computed.\n"
    "- business_days: a date that is not a business day or is a holiday is rejected and the next business day is offered.\n"
    "- offer_amounts: an amount below the floor or above the maximum is rejected and the limit is offered; an amount "
    "in between is accepted.\n"
    "- weekday_reading: how \"next <weekday>\" and \"this <weekday>\" become a date.\n"
    "- invalid_offer_limit: a product is given up after too many offers that fail these checks.\n"
    "- identity_attempts: wrong identity answers are counted and the check stops when none are left.\n"
    "- closing_outcome: the closing table picks the outcome and reason; the goodbye sentence is said first; the "
    "closing tool is called exactly once and last; a row marked to win over a promise wins.\n"
    "- persuasion_attempts: persuasion attempts are counted per product (each product starts again), a refusal "
    "uses one, and the product ends when they are used up. Not what the agent proposes on each attempt.\n"
    "- product_refusal: the products are discussed one by one in the account tool's order; a refusal ends only "
    "the product being discussed and the call moves on to the next one.\n"
    "- product_notes: a note is written for every product that ends without a promise, with its reason.\n"
    "- product_notes_skip: no notes at all on the outcomes the note rule lists to skip (for example a transfer).\n"
    "Leave enforced_by out for anything the agent must say, ask, propose or decide, and for closing logic the table "
    "cannot express. A rule that covers two checks, or a check and an instruction, is split into separate rules.",
    ("{documents}", "{contract}", "{call_variables}"),
)

_RULE_SHAPE = '{"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}'

EXTRACT_OPENING_IDENTITY_TASK = PromptDefinition(
    "EXTRACT_OPENING_IDENTITY_TASK",
    "Extracts the agent identity, opening, third-party handling, identity check and global rules.",
    "builder model", "builder/extract.py — extraction call 'opening_identity'",
    "Extract the sections agent, opening, third_party, identity and global_rules. RULE means " + _RULE_SHAPE + ".\n"
    "Return this JSON shape:\n"
    "{\n"
    ' "agent": {"name": "how the agent presents itself", "language": "language of the call", '
    '"introduction": RULE (text: the exact first sentence the agent says to the customer, word for word: who is '
    'calling, for whom, recording notice. Not an instruction such as "Say you are ..."), '
    '"wait_line": "one short sentence in the language of the call, said while the account is looked up after '
    'identity is verified, for example a thank-you and a request to wait; no debt details"},\n'
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
    '"route": "stay | end", "outcome": "...", "reason": "...", "source": "..."}], '
    '"callback_window": {"days_ahead": integer, "day_unit": "business | calendar", "earliest_time": "HH:MM", '
    '"latest_time": "HH:MM", "after_now": true | false, "max_outside_asks": integer, '
    '"outside_close_value": "intent value with route end", "source": "excerpt"}}\n'
    "   (what the person who is not the customer may want. route end: the call closes with that outcome and reason, "
    "with no tool. A callback that is booked with a tool keeps route stay: the program closes it from the tool result.\n"
    "   callback_window: when a callback may be booked, copied from the documents; omit it when they set no limit. "
    "days_ahead: how many days after today are allowed (0 = today only; \"today or the next business day\" = 1 with "
    "day_unit business). earliest_time/latest_time: the allowed time of day, both included, 24-hour. after_now: true "
    "when the time must be later than the call's current time. max_outside_asks: how many times the agent asks for "
    "another time after an offer outside the window (0 if the documents do not say). outside_close_value: the intent "
    "value (route end) to close with when the next offer is still outside or no clear time is given; required "
    "with a window (if the documents name no row for it, the closest no-callback value). "
    "The program resolves and checks the person's day and time in code; the model never types the date.)\n"
    ' "identity": {\n'
    '  "rules": [RULE] (limits, refusal handling, what never to do before all questions pass),\n'
    '  "questions": [{"field": "value of the identity tool\'s question selector enum", "ask": RULE, '
    '"answer_format": RULE (how to convert the spoken answer into the tool format)}] (in the order asked),\n'
    '  "verified_field": "identity tool response field (boolean) that is true when the whole check passed",\n'
    '  "attempts_left_field": "identity tool response field (integer) with the wrong answers or attempts left",\n'
    '  "answer_verified_field": "identity tool response field (boolean) for the answer just checked",\n'
    '  "failed_answer_instruction": RULE (what to do after a failed answer, including any hint the tool returns),\n'
    '  "exhausted_say": RULE (text: the exact words said to the customer when no attempts are left, word for word, '
    'not an instruction such as "Tell the customer ...")\n'
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
    '"product_id_field": "field of one product item that identifies it for the promise tool", '
    '"product_kind_field": "product item field with the kind of product, or \"\"", '
    '"product_label_field": "product item field the customer recognises the product by, such as its last digits, '
    'or \"\""},\n'
    ' "negotiation": {"rules": [RULE] (what to ask first, what counts as a refusal, persuasion attempts and what each '
    "proposes, what never to offer, per-product handling),\n"
    '  "intents": [{"value": "snake_case code", "meaning": "...", "route": "readback | end | stay", '
    '"outcome": "...", "reason": "...", "per_product": true or false, "uses_attempt": true or false, '
    '"source": "..."}]\n'
    "   (the customer's state after each turn. route readback: an agreed date and amount are ready to read back. "
    "end: the customer refuses any arrangement after the allowed attempts; give the closing-table outcome and reason. "
    "stay: keep negotiating. At least one readback and one end value. Only refusing to pay or to talk may use "
    "route end. per_product true (route end only): the refusal ends only the product being discussed when the "
    "documents handle several products one at a time; the call goes on with the next product and closes with this "
    "outcome only when no product is left. uses_attempt true (route stay only): a flat refusal or a non-answer that "
    "uses one persuasion attempt; code counts these per product when the offer section gives persuasion_attempts. "
    "Leave both false when the documents give no such rule. Situations with their own sentence or tool (the payment was already made, the debt is denied, "
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
    "not invalid-offer limits),\n"
    '  "persuasion_attempts": [{"when": [CONDITION], "value": integer, at least 1}] (the number of persuasion '
    "attempts after a flat refusal, per product, when the documents give it, for example per band; first match "
    "wins; [] when the documents give no number)\n"
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
    ' "closing": {"rules": [RULE] (how the call ends; most are enforced_by closing_outcome. An instruction for '
    "what the agent does during the call, such as notes or transfers, belongs to the step where it happens, not here), "
    '"outcome_field": "closing tool request field for the outcome", '
    '"reason_field": "closing tool request field for the reason", '
    '"product_notes": null or {"tool": "note tool name", "product_field": "note tool request field for the product id", '
    '"reason_field": "note tool request field for the reason", "reasons": ["every reason value the documents allow"], '
    '"refused_reason": "reason for a product the customer turned down or never agreed to", '
    '"failed_reason": "reason for a product whose promise could not be recorded", '
    '"skip_outcomes": ["call outcomes after which no note is added at all, for example a transfer"], '
    '"outcome_from_notes": null or {"all_reason": "the note reason that, on every product, gives its own row", '
    '"all_outcome": "outcome of that row", "all_outcome_reason": "reason of that row or \\"\\"", '
    '"otherwise_outcome": "outcome used otherwise, with the reason of the first product in account order whose note '
    'is another reason", "source": "excerpt"} (only when the documents derive the call outcome from the notes when '
    'no promise was recorded; null otherwise), '
    '"source": "excerpt"} (only when the documents require a note for each product that ended without a promise; '
    "code then writes those notes before the closing tool; null otherwise)},\n"
    ' "outcomes": [{"outcome": "...", "reason": "... or \\"\\"", "when": RULE, "say": RULE (text: the exact words '
    "the agent says to the customer before the closing tool, word for word, read aloud as written; include every "
    "sentence the brief requires in that situation and end with a goodbye. Never an instruction such as "
    "\"Thank the customer and say goodbye.\"; write \"Thank you for your time. Goodbye.\" instead), "
    '"wins_over_promise": true or false (true only if this row is used even after a promise was recorded), '
    '"states": ["call-end state names below that close with this row"]}]\n'
    "   (one row per outcome and reason pair the brief allows; every pair from the closing table.)\n"
    ' "special_paths": [{"id": "snake_case", "when": RULE (what the customer says), "say": RULE (text: the exact words said to the customer, read aloud as written; never an instruction to the agent), '
    '"ask": RULE (optional; leave the key out unless the documents require one question before acting, for example '
    "whether the agent can help first or whether the customer wants to be connected. The agent says it to the customer "
    'and waits for the answer, so it must be one question ending with "?", never an instruction), '
    '"on_decline": "id of another special path" (optional, only with ask: the closing path the documents give when '
    'the customer does not want what this path does after the question; leave it out when a no simply goes on with the call), '
    '"say_first": true (optional, only with ask: the documents say the say line when the situation starts, before the question, '
    'for example one sentence of sympathy before an offer; leave it out when say is what the agent says when it acts after the question), '
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
    "- Every say and ask is the customer's words, read aloud as written: no \"the customer\", no instruction "
    "to the agent such as \"Say ...\", \"Tell ...\", \"Offer ...\" or \"Do not ...\".\n"
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
    THIRD_PARTY_INTENT_DESCRIPTION,
    THIRD_PARTY_CUSTOMER_DESCRIPTION,
    THIRD_PARTY_CLOSE_KIND_DESCRIPTION,
    NO_SECURITY_QUESTIONS_LINE,
    NO_GOODBYE_LINE,
    SIDE_QUESTION_LINE,
    SIDE_QUESTION_ITEM,
    IDENTITY_TASK_TEMPLATE,
    NEGOTIATION_TASK_TEMPLATE,
    OFFER_VERDICT_MESSAGES,
    OFFER_PRODUCT_NAME_DESCRIPTION,
    OFFER_REFUSED_PRODUCTS_DESCRIPTION,
    READBACK_LINE,
    READBACK_ITEM,
    CONFIRM_READBACK_SAID_LINE,
    CUSTOMER_ENDS_CALL_INTENT,
    GOODBYE_CHOICE_DESCRIPTION,
    CONFIRM_TASK_TEMPLATE,
    ACCOUNT_WAIT_LINE,
    REVISE_ASK_LINE,
    READBACK_RESUME_LINE,
    PERSUASION_STATE_LINE,
    PERSUASION_PRODUCT_LINE,
    PRODUCT_INTENT_DESCRIPTION,
    PRODUCT_END_COUNTED_DESCRIPTION,
    CLOSING_FALLBACK_SAY,
    SPECIAL_PATH_TASK_TEMPLATE,
    SPECIAL_CLOSE_TOOL_TASK_TEMPLATE,
    SPECIAL_ASK_TASK_TEMPLATE,
    SPECIAL_SAY_FALLBACK,
    SPECIAL_TOOL_FAILED_SAY,
    PROMISE_NOT_ALL_RECORDED_SAY,
    SPECIAL_ASK_PHRASED_TEMPLATE,
    SPECIAL_SAY_FIRST_LINE,
    SPECIAL_CHOICE_DESCRIPTION,
    SPECIAL_TOPIC_DESCRIPTION,
    CALLBACK_COLLECT_RULE,
    CALLBACK_DAY_DESCRIPTION,
    CALLBACK_TIME_DESCRIPTION,
    CALLBACK_OUTSIDE_SAY,
    CALLBACK_UNCLEAR_SAY,
    CALLBACK_TIME_ASK_SAY,
    THIRD_PARTY_CLOSE_REASK_SAY,
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
