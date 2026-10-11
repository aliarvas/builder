# Prompts

Generated from `builder/prompts.py`. Do not edit by hand; edit the code and regenerate.

## PHONE_AGENT_SYSTEM_PROMPT

- Purpose: Sets the phone agent's global identity, language, brevity, and honesty rules.
- Receiver: phone agent
- Used at: builder/workflow.py — workflow-level system_prompt
- Approximate tokens: ~76 (characters ÷ 4)

```text
You are a bank's digital assistant on an outbound phone call. Speak English. Keep every turn concise and truthful. Call at most one tool per message. After every tool result, speak to the customer or call the next required tool. Never claim an action succeeded unless the tool result says it succeeded.
```

## PHONE_AGENT_TASK_MESSAGE_TEMPLATE

- Purpose: Gives the phone agent its runtime brief, call variables, and tool-use instructions.
- Receiver: phone agent
- Used at: builder/workflow.py — call node task_message
- Approximate tokens: ~90 static + `{brief_text}` characters ÷ 4 at runtime
- Budget: **OVER BUDGET** — the complete runtime brief is inserted and can exceed 1,500 tokens.

```text
You are on a phone call. Follow the supplied bank brief exactly.

Call variables: customer_id={{customer_id}}, first_name={{first_name}}, last_name={{last_name}}, title={{title}}, now={{now}}.

When a rule requires a tool, call that tool; saying an action happened is not enough. Use every returned result field exactly; do not invent values.

# BANK BRIEF

{brief_text}
```

## TOOL_RESULT_FAILURE_MESSAGE

- Purpose: Tells the phone agent that a tool action was not carried out without overriding retry policy.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — generic API post-hook
- Approximate tokens: ~42 (characters ÷ 4)

```text
The action was NOT carried out. Do not say it was done. Follow the brief's rule for a failed action (retry if the brief allows it, otherwise tell the customer plainly).
```

## TOOL_RESULT_FALSE_FIELDS_TEMPLATE

- Purpose: Makes negative boolean result fields explicit after an otherwise successful API call.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — generic API post-hook
- Approximate tokens: ~41 static + `{fields}` characters ÷ 4 at runtime

```text
The action ran, but these result fields are false: {fields}. Treat each as NOT satisfied; do not proceed as if it passed. Read every field of the result before speaking.
```

## TOOL_RESULT_UNCLEAR_MESSAGE

- Purpose: Prevents success claims when a tool response does not clearly prove success.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — generic API post-hook
- Approximate tokens: ~42 (characters ÷ 4)

```text
The result does not clearly show that the action succeeded. Check every result field and do not claim success unless the result clearly proves it. Do not invent values.
```

## TOOL_RESULT_OK_MESSAGE

- Purpose: Directs the phone agent after a clearly successful tool result.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — generic API post-hook
- Approximate tokens: ~38 (characters ÷ 4)

```text
The action ran and returned ok. Read the other result fields exactly, then speak to the customer or call the next required tool. Do not invent values.
```

## TOOL_CALL_TRIGGER

- Purpose: Reminds the phone agent that describing an API action does not execute it.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — tool description
- Approximate tokens: ~22 (characters ÷ 4)

```text
CALL this tool whenever the situation above applies; saying you did it is not enough.
```

## TOOL_FIELD_DETAILS_TEMPLATE

- Purpose: Introduces concise OpenAPI field constraints in a tool description.
- Receiver: phone agent
- Used at: builder/tools_from_openapi.py — tool description
- Approximate tokens: ~2 static + `{field_details}` characters ÷ 4 at runtime

```text
Fields: {field_details}
```

## MULTI_STEP_SYSTEM_PROMPT_TEMPLATE

- Purpose: Sets spec-derived identity and global rules for the multi-step phone agent.
- Receiver: phone agent
- Used at: builder/workflow.py — spec workflow system_prompt
- Approximate tokens: ~73 static + `{agent_name}` characters ÷ 4 + `{language}` characters ÷ 4 + `{rules}` characters ÷ 4 at runtime

```text
You are {agent_name}. Speak {language}. Keep every turn concise and truthful. Call at most one tool per message. Never claim an action succeeded, or a note or callback was recorded, unless its tool returned ok true; never say a payment or promise was recorded unless create_promise returned ok true.
Global rules:
{rules}
```

## OPENING_TASK_TEMPLATE

- Purpose: Opens the call and identifies who answered.
- Receiver: phone agent
- Used at: builder/workflow.py — opening
- Approximate tokens: ~111 static + `{introduction}` characters ÷ 4 + `{address}` characters ÷ 4 + `{question}` characters ÷ 4 + `{unclear}` characters ÷ 4 + `{forbidden}` characters ÷ 4 + `{rules}` characters ÷ 4 at runtime

```text
Your first words in this call, whatever the customer said, and only once: {introduction}
If you already gave the introduction in this call, do not repeat it: answer briefly and ask the question again.
The person to ask for is {address}. Use these words when you address them.
Ask: {question}
If they only greet you or check the line (for example "Hello?"), that is not an answer: reply briefly and ask the question again.
If unclear: {unclear}
Before verification, do not say: {forbidden}
Rules:
{rules}
```

## OPENING_REASK_TASK_TEMPLATE

- Purpose: Asks the opening question again after an unclear answer, without a second introduction.
- Receiver: phone agent
- Used at: builder/workflow.py — opening_reask
- Approximate tokens: ~83 static + `{address}` characters ÷ 4 + `{question}` characters ÷ 4 + `{unclear}` characters ÷ 4 + `{forbidden}` characters ÷ 4 + `{rules}` characters ÷ 4 at runtime

```text
You already gave the introduction earlier in this call. Do not repeat it unless they ask who is calling.
The person to ask for is {address}. Use these words when you address them.
Ask again, briefly: {question}
If they only greet you or check the line, reply briefly and ask the question again.
If unclear: {unclear}
Before verification, do not say: {forbidden}
Rules:
{rules}
```

## WHO_ANSWERED_DESCRIPTION

- Purpose: Extraction description of the who-answered variable in the opening steps; every value is described (F-071). A line whose value list is empty is left out.
- Receiver: extraction model
- Used at: builder/workflow.py — opening and opening_reask extraction_schema
- Approximate tokens: ~137 static + `{confirm}` characters ÷ 4 + `{unclear_rule}` characters ÷ 4 + `{other}` characters ÷ 4 + `{close}` characters ÷ 4 + `{stay}` characters ÷ 4 + `{greeting}` characters ÷ 4 at runtime

```text
Who answered the call.
{confirm}: the person clearly confirms they are the customer. The documents' rule: {unclear_rule}
{other}: only when the person clearly says they are not the customer (for example someone else's name, "she is not here", "I am his wife").
{close}: only when the person clearly says what that value names.
{stay}: anything else that does not confirm, including a garbled or half-heard answer, an answer in another language, or a question back.
{greeting}: the person only greets or checks the line (for example "Hello?" or "Who is this?") and has not answered the question yet.
```

## THIRD_PARTY_TASK_TEMPLATE

- Purpose: Handles a person other than the customer.
- Receiver: phone agent
- Used at: builder/workflow.py — third_party
- Approximate tokens: ~20 static + `{rules}` characters ÷ 4 at runtime

```text
Handle the third-party response without disclosing protected details.
Rules:
{rules}
```

## THIRD_PARTY_INTENT_DESCRIPTION

- Purpose: Restricts third-party closing intents to situations named by the spec's closing values (F-064).
- Receiver: extraction model
- Used at: builder/callback.py — third_party intent extraction field
- Approximate tokens: ~86 static + `{close_values}` characters ÷ 4 at runtime

```text
The third party's current intent. Closing values are: {close_values}. Choose one when the person's message clearly states the situation that value names. A question, an offer to pay, or a request for account or payment information is not a closing situation: choose none so the agent can decline to disclose details and ask when the customer can be reached.
```

## THIRD_PARTY_CUSTOMER_DESCRIPTION

- Purpose: Adds the framework value for a third party who is in fact the customer (F-069).
- Receiver: extraction model
- Used at: builder/workflow.py — appended to the third_party intent extraction field
- Approximate tokens: ~23 static + `{value}` characters ÷ 4 at runtime

```text
{value}: the person says they are the customer themselves, or the customer has come to the phone.
```

## THIRD_PARTY_CLOSE_KIND_DESCRIPTION

- Purpose: Provides an independent guard signal for third-party closing intents (F-064).
- Receiver: extraction model
- Used at: builder/callback.py — third_party close-kind extraction field
- Approximate tokens: ~109 static + `{close_values}` characters ÷ 4 at runtime

```text
Classify only the third party's last message. Closing values are: {close_values}. Choose explicit_close when the person clearly states a situation named by one of those values, for example a refusal of a callback, that the customer cannot be reached, or "she doesn't want to be called". Choose other for every question, offer to pay, request for information, vague reply, or non-answer, for example "I can pay it myself if you tell me the amount".
```

## NO_SECURITY_QUESTIONS_LINE

- Purpose: Keeps security questions out of the steps before identity verification (F-070).
- Receiver: phone agent
- Used at: builder/workflow.py — opening, opening_reask, third_party and third_party_ask task_message
- Approximate tokens: ~27 (characters ÷ 4)

```text
Never ask security questions or for personal data in this step; only the program verifies identity, later.
```

## NO_GOODBYE_LINE

- Purpose: Keeps the goodbye in the closing step (F-072).
- Receiver: phone agent
- Used at: builder/workflow.py — every conversation task_message except the step that says the closing sentence
- Approximate tokens: ~18 (characters ÷ 4)

```text
Never say goodbye or end the call yourself; the program closes the call.
```

## IDENTITY_TASK_TEMPLATE

- Purpose: Asks ordered identity questions and uses the verification tool.
- Receiver: phone agent
- Used at: builder/workflow.py — identity
- Approximate tokens: ~182 static + `{questions}` characters ÷ 4 + `{answer_verified}` characters ÷ 4 + `{failed_answer}` characters ÷ 4 + `{wait_line}` characters ÷ 4 + `{attempts_left}` characters ÷ 4 + `{exhausted_say}` characters ÷ 4 + `{rules}` characters ÷ 4 at runtime

```text
Ask these security questions one at a time, in order. Call the identity tool with each answer:
{questions}
Convert the customer's spoken answer into the tool format yourself. Never ask the customer to say a technical format.
After each tool result:
- {answer_verified} is true: acknowledge briefly and ask the next question. After the last question, ask nothing more; say the answers matched, then say: {wait_line} Give no account details yet.
- {answer_verified} is false: say the answer did not match. Do not thank them as if it passed. Ask the same question again; never move to the next question until this one is verified. {failed_answer}
- The action was not carried out: ask for the same answer again; it is not a wrong answer.
- {attempts_left} is 0: {exhausted_say} Ask nothing more and give no account details.
Rules:
{rules}
```

## NEGOTIATION_TASK_TEMPLATE

- Purpose: Discusses the account and obtains a date and an amount per product.
- Receiver: phone agent
- Used at: builder/workflow.py — negotiate
- Approximate tokens: ~262 static + `{rules}` characters ÷ 4 at runtime

```text
Calendar: {{calendar_text}}
Account facts: {{products_facts}}
Last offer verdict: {{offer_verdict}}. Last offer check: {{offer_message}}
Offers accepted so far: {{offers_summary}}
Use only these dates and amounts; never work out a date or an amount yourself. Name each product as the account facts do, never by a list number. Never read an internal id aloud. Never mention internal step, tool or variable names, and never write code.
The bank system checks every date and amount the customer names and has already said the last offer check to the customer: do not repeat it; answer the customer, offering exactly a date or an amount it names. Verdict none: propose or ask, but never say whether a date or an amount is allowed. Never state a limit yourself unless the last offer check names it.
A checked offer is not recorded: never say a payment or promise was recorded.
Get a concrete date and amount. If the customer names only a date, the amount you last proposed applies. Not paying on one date is not a refusal: ask for another date.
Rules:
{rules}
```

## OFFER_VERDICT_MESSAGES

- Purpose: One customer-facing sentence per offer-check verdict, spoken word for word after the check.
- Receiver: customer (fixed spoken line via offer_message)
- Used at: builder/offer_check.py — check_offer; builder/workflow.py — offer_say
- Approximate tokens: ~207 (characters ÷ 4)

```text
ok: Thank you, that works for the [product].
more: Now let us look at the [next]. The amount due is [next_amount]. Could you pay [next_amount]?
missing: Could you tell me the exact day you would like to pay?
amount_missing: Could you pay [amount]?
product_unknown: Which of your products is this payment for?
date_too_early: I can only record a date from [date]. Would [date] work for you?
date_too_late: The latest date I can record for the [product] is [date]. Would [date] work for you?
date_not_business_day: That day is not a business day. The next possible day is [date]. Would that work for you?
date_ambiguous: Do you mean [date]?
amount_too_low: The lowest amount I can record for the [product] is [amount]. Could you pay [amount]?
amount_too_high: The amount due on the [product] is [amount]. Could you pay [amount]?
```

## CONFIRM_TASK_TEMPLATE

- Purpose: Reads back the checked offers once and asks for one confirmation; the program records them (F-063).
- Receiver: phone agent
- Used at: builder/workflow.py — confirm_record
- Approximate tokens: ~137 static + `{rules}` characters ÷ 4 at runtime

```text
Checked offers: {{offers_summary}}
Read all of these back once, in these words, and ask for one clear confirmation. Never say the product number in square brackets. After a clear yes, say nothing more: the program records the promises and the closing tells the customer. Never say a promise is recorded. Do not change a date or an amount yourself; if the customer wants a change, ask for the new value.
You have no tool here: where a rule below speaks of calling, retrying or checking the promise tool, the program does that after the yes.
Rules:
{rules}
```

## ACCOUNT_WAIT_LINE

- Purpose: Line said after identity passed, before the account lookup, when the spec gives none (F-043, F-050).
- Receiver: phone agent (in the identity step prompt)
- Used at: builder/workflow.py — identity step, {wait_line}
- Approximate tokens: ~13 (characters ÷ 4)

```text
Thank you. One moment while I check your account.
```

## REVISE_ASK_LINE

- Purpose: Fixed line when the customer wants to change the read-back (F-053).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/workflow.py — revise_ask
- Approximate tokens: ~14 (characters ÷ 4)

```text
Of course. Which date or amount would you like instead?
```

## PERSUASION_STATE_LINE

- Purpose: Tells the negotiation step which persuasion attempt it is on (F-062).
- Receiver: phone agent
- Used at: builder/product_notes.py — negotiate (only when the spec gives persuasion attempts)
- Approximate tokens: ~39 static + `{attempt}` characters ÷ 4 at runtime

```text
Persuasion attempt on this product, counted by the bank system: {attempt} (0: none yet). The bank system moves on to the next product when its attempts are used up.
```

## PRODUCT_INTENT_DESCRIPTION

- Purpose: Extraction meaning of the per-product refusal values (F-062).
- Receiver: extraction model
- Used at: builder/product_notes.py — negotiate extraction field
- Approximate tokens: ~50 static + `{product_end}` characters ÷ 4 + `{attempt}` characters ÷ 4 at runtime

```text
Values {product_end} end only the product being discussed; the call goes on with the other products. Values {attempt} are a flat refusal or a non-answer about the product being discussed, which uses one persuasion attempt.
```

## PRODUCT_END_COUNTED_DESCRIPTION

- Purpose: Extraction note when the spec gives persuasion attempts: code decides when a product ends (AB-FRESH).
- Receiver: extraction model
- Used at: builder/product_notes.py — negotiate extraction field (only with persuasion attempts)
- Approximate tokens: ~50 static + `{product_end}` characters ÷ 4 + `{attempt}` characters ÷ 4 at runtime

```text
The bank system counts the persuasion attempts and ends the product only when they are used up; while attempts are left, {product_end} also uses one attempt. For any no about the product being discussed, choose {attempt}.
```

## CLOSING_FALLBACK_SAY

- Purpose: Spoken goodbye when the matched outcome row has an empty closing sentence.
- Receiver: phone agent (fixed spoken line)
- Used at: builder/workflow.py — closing code step (closing_sentence)
- Approximate tokens: ~9 (characters ÷ 4)

```text
Thank you for your time. Goodbye.
```

## SPECIAL_PATH_TASK_TEMPLATE

- Purpose: Handles a spec-defined special path whose tool needs a value only the conversation can give.
- Receiver: phone agent
- Used at: builder/workflow.py — global special_<id> (model-filled tool only)
- Approximate tokens: ~64 static + `{when}` characters ÷ 4 + `{say}` characters ÷ 4 at runtime

```text
The customer said: {when}
Call the available tool once before claiming any action. Fill only the fields it asks for, from this call. Only if the tool result says ok true, say exactly: {say}
If it did not return ok true, do not say anything was recorded or completed.
```

## SPECIAL_CLOSE_TOOL_TASK_TEMPLATE

- Purpose: Handles a special path that ends the call and whose tool needs a value only the conversation can give. The closing step speaks the path's line after the tool, so this step says nothing then (F-056 fix).
- Receiver: phone agent
- Used at: builder/workflow.py — special_<id> (model-filled tool, then close)
- Approximate tokens: ~77 static + `{when}` characters ÷ 4 at runtime

```text
The customer said: {when}
Call the available tool once. Fill only the fields it asks for, from this call. If a field is not known yet, ask only for it and call no tool.
When you call the tool, say nothing before or after it: the next step speaks to the customer. Never say that anything was recorded or completed.
```

## SPECIAL_ASK_TASK_TEMPLATE

- Purpose: Waits for the answer to a special path's first question.
- Receiver: phone agent
- Used at: builder/workflow.py — global special_<id> with ask
- Approximate tokens: ~21 static + `{ask}` characters ÷ 4 at runtime

```text
You asked: {ask}
Wait for the answer. Do not call any tool and do not promise anything.
```

## SPECIAL_SAY_FALLBACK

- Purpose: Spoken instead of a special path's line when the spec's line is an instruction to the agent (F-047).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/workflow.py — special path say fallback
- Approximate tokens: ~8 (characters ÷ 4)

```text
Thank you for letting me know.
```

## SPECIAL_TOOL_FAILED_SAY

- Purpose: Said before the closing sentence when a closing special path's tool failed and the spec has no line for that state (F-059).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/workflow.py — closing code, special_tool_failed
- Approximate tokens: ~14 (characters ÷ 4)

```text
I am sorry, I could not complete that request right now.
```

## PROMISE_NOT_ALL_RECORDED_SAY

- Purpose: Said before the closing sentence when a promise could not be recorded and the outcome row is not the spec's own row for that (for example another promise was recorded) (F-063).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/workflow.py — closing code, promise_failed
- Approximate tokens: ~12 (characters ÷ 4)

```text
I am sorry, I could not record every promise.
```

## SPECIAL_ASK_PHRASED_TEMPLATE

- Purpose: Lets the agent phrase a special path's question when the spec gives an instruction instead of words (F-047).
- Receiver: phone agent
- Used at: builder/workflow.py — global special_<id> with ask (fallback)
- Approximate tokens: ~34 static + `{ask}` characters ÷ 4 at runtime

```text
Ask the customer this as one short question, in your own words: {ask}
Wait for the answer. Do not call any tool and do not promise anything.
```

## CALLBACK_COLLECT_RULE

- Purpose: Added to the third-party step when the program books callbacks itself (F-055 review finding 3).
- Receiver: phone agent
- Used at: builder/callback.py — third_party and third_party_ask task
- Approximate tokens: ~65 (characters ÷ 4)

```text
To arrange a callback, get the day and the time of day when the customer can be reached, in the person's own words; if they give only one of them, ask for the other. Never say a callback is booked or arranged: the program books it and the closing tells them.
```

## CALLBACK_DAY_DESCRIPTION

- Purpose: Extraction field in the third-party step: the person's words for the callback day (F-055).
- Receiver: phone agent (extraction)
- Used at: builder/callback.py — third_party extraction callback_day_text
- Approximate tokens: ~59 (characters ÷ 4)

```text
Copy the words for the day when the customer can be called back from the person's last message, unchanged (for example "tomorrow", "Friday", "the 15th"). Do not resolve relative dates with the system clock. Empty if they name no day.
```

## CALLBACK_TIME_DESCRIPTION

- Purpose: Extraction field in the third-party step: the person's words for the callback time (F-055).
- Receiver: phone agent (extraction)
- Used at: builder/callback.py — third_party extraction callback_time_text
- Approximate tokens: ~64 (characters ÷ 4)

```text
Copy the words for the time of day when the customer can be called back from the person's last message, unchanged, with any morning/afternoon/evening or am/pm words (for example "around eleven in the morning", "3pm", "14:30"). Empty if they name no time.
```

## CALLBACK_OUTSIDE_SAY

- Purpose: Spoken when the callback time the person gave is outside the callback window (F-055); code fills {window}.
- Receiver: phone agent (fixed spoken line)
- Used at: builder/callback.py — third_party_ask entry line
- Approximate tokens: ~20 static + `{window}` characters ÷ 4 at runtime

```text
I am sorry, we cannot call back then. We can call back {window}. What time would suit?
```

## CALLBACK_UNCLEAR_SAY

- Purpose: Spoken when the callback day or time could not be understood (F-055).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/callback.py — third_party_ask entry line
- Approximate tokens: ~17 (characters ÷ 4)

```text
Sorry, could you tell me the day and the time when we can call back?
```

## CALLBACK_TIME_ASK_SAY

- Purpose: Spoken when the person named a callback day but no time; the day is kept for the next turn (F-055).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/callback.py — third_party_ask entry line
- Approximate tokens: ~12 (characters ÷ 4)

```text
Thank you. At what time of day can we call back?
```

## THIRD_PARTY_CLOSE_REASK_SAY

- Purpose: One bounded re-ask when a third-party closing intent lacks an explicit refusal (F-064).
- Receiver: phone agent (fixed spoken line)
- Used at: builder/callback.py — third_party_ask entry line
- Approximate tokens: ~20 (characters ÷ 4)

```text
I cannot discuss account or payment details. When can the customer be reached?
```

## CONVERSATION_NO_TOOL_RULE

- Purpose: Explicitly forbids tool calls in a conversation step that exposes no tools.
- Receiver: phone agent
- Used at: builder/workflow.py — every tool-free conversation task_message and loop_prompt
- Approximate tokens: ~17 (characters ÷ 4)

```text
Tool-use rule for this turn: No tool call is allowed in this turn.
```

## CONVERSATION_TOOL_RULE_TEMPLATE

- Purpose: Names an exposed conversation tool exactly and states its call condition.
- Receiver: phone agent
- Used at: builder/workflow.py — every tool-enabled conversation task_message and loop_prompt
- Approximate tokens: ~47 static + `{tool_name}` characters ÷ 4 at runtime

```text
Tool-use rule for this turn: Call {tool_name} only when the customer's response meets this step's stated condition for that action and all required tool inputs are known; do not call it otherwise.
```

## EXTRACTION_SYSTEM_PROMPT

- Purpose: Sets the builder model's job: turn a bank collections brief into spec data with sources.
- Receiver: builder model
- Used at: builder/extract.py — system prompt of every extraction call
- Approximate tokens: ~274 (characters ÷ 4)

```text
You turn a bank's collections brief into structured data for an outbound phone agent. A program builds the agent from your data, so every value must be exact.
- Use only the documents given. Never invent a rule, value, outcome, reason, queue, date or sentence. If the documents give no value for a field, follow the field's fallback instruction and say so in sources.
- The documents come in order. A later document, memo or correction overrides an earlier one: use only the newer value and list the change in overrides.
- Every rule has a source: a short verbatim excerpt (at most 25 words) copied from the documents, so a reader can find it with a text search.
- Do no arithmetic. Store counts, units and conditions as data; code computes dates and amounts.
- Codes and enum values are copied exactly as written (same spelling and case). Tool field names come only from the tool contract.
- Rule texts are short instructions to the phone agent, in English, one idea each. Sentences the agent must say word for word are copied exactly.
- Reply with one JSON object only: no prose, no code fence.
```

## EXTRACTION_CONTEXT_TEMPLATE

- Purpose: Shared first message of every extraction call: the documents, the tool contract and the call variables.
- Receiver: builder model
- Used at: builder/extract.py — shared, cached context block
- Approximate tokens: ~681 static + `{documents}` characters ÷ 4 + `{contract}` characters ÷ 4 + `{call_variables}` characters ÷ 4 at runtime

```text
# DOCUMENTS (in order; later overrides earlier)

{documents}

# TOOL CONTRACT (from the OpenAPI file)

{contract}

# CALL VARIABLES (known when the call starts)

{call_variables}

# PHONE AGENT SKELETON

The program builds these steps; your data fills them: opening (introduction, find out who answered) -> third_party (someone else answered) or identity (security questions with the identity tool) -> account (fetch the late products) -> negotiate (get a date and an amount per product; code checks each offer against the date and amount rules) -> confirm_record (read back, confirm, record each promise) -> closing (one goodbye sentence, then the closing tool once). Special paths (for example a transfer request) can interrupt the steps they are available in. The closing outcome comes from a table that maps call-end states to outcome rows.

# RULES THE PROGRAM ALREADY ENFORCES

Any RULE may carry "enforced_by" when program code already guarantees exactly that rule. Such a rule can be left out of the phone agent's prompt to save room; it stays in the spec. Allowed values:
- offer_dates: a promise date before the earliest or after the latest allowed date is rejected and the allowed date is offered; each product's deadline is computed.
- business_days: a date that is not a business day or is a holiday is rejected and the next business day is offered.
- offer_amounts: an amount below the floor or above the maximum is rejected and the limit is offered; an amount in between is accepted.
- weekday_reading: how "next <weekday>" and "this <weekday>" become a date.
- invalid_offer_limit: a product is given up after too many offers that fail these checks.
- identity_attempts: wrong identity answers are counted and the check stops when none are left.
- closing_outcome: the closing table picks the outcome and reason; the goodbye sentence is said first; the closing tool is called exactly once and last; a row marked to win over a promise wins.
- persuasion_attempts: persuasion attempts are counted per product (each product starts again), a refusal uses one, and the product ends when they are used up. Not what the agent proposes on each attempt.
- product_refusal: the products are discussed one by one in the account tool's order; a refusal ends only the product being discussed and the call moves on to the next one.
- product_notes: a note is written for every product that ends without a promise, with its reason.
- product_notes_skip: no notes at all on the outcomes the note rule lists to skip (for example a transfer).
Leave enforced_by out for anything the agent must say, ask, propose or decide, and for closing logic the table cannot express. A rule that covers two checks, or a check and an instruction, is split into separate rules.
```

## EXTRACT_OPENING_IDENTITY_TASK

- Purpose: Extracts the agent identity, opening, third-party handling, identity check and global rules.
- Receiver: builder model
- Used at: builder/extract.py — extraction call 'opening_identity'
- Approximate tokens: ~1252 (characters ÷ 4)

```text
Extract the sections agent, opening, third_party, identity and global_rules. RULE means {"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}.
Return this JSON shape:
{
 "agent": {"name": "how the agent presents itself", "language": "language of the call", "introduction": RULE (text: the exact first sentence the agent says to the customer, word for word: who is calling, for whom, recording notice. Not an instruction such as "Say you are ..."), "wait_line": "one short sentence in the language of the call, said while the account is looked up after identity is verified, for example a thank-you and a request to wait; no debt details"},
 "opening": {
  "rules": [RULE] (other opening rules: what may be said before verification, how to answer questions about who or what is calling),
  "confirmation_question": RULE (how to ask whether the intended customer is speaking),
  "unclear_instruction": RULE (what to do when the answer does not confirm it),
  "forbidden_before_verification": ["word or topic that must not be said before identity is verified"],
  "address_with": ["call variable names used to address the customer, in spoken order"],
  "max_unclear_asks": integer (how many times in total the confirmation question is asked, first ask included, before the call closes as unclear),
  "answers": [{"value": "snake_case code", "meaning": "...", "route": "verify | other_person | ask_again | end", "outcome": "...", "reason": "...", "source": "..."}]
   (every kind of answer to the confirmation question. route verify: the customer confirmed, go to the identity check. other_person: someone else answered. ask_again: unclear, ask again. end: the call closes right away; outcome and reason are the closing-table values for it, reason "" when the table has none. Exactly one value with route ask_again. Do not add a value for a bare greeting; the program adds it. Always include one value with route end for a person who refuses to talk or to confirm who they are; close it with the row the documents give for refusing before verification, or, if they name none, the closest row. If the documents do not name this case, its source is "derived: <why this row>" instead of an excerpt.)
 },
 "third_party": {"rules": [RULE], "intents": [{"value": "snake_case code", "meaning": "...", "route": "stay | end", "outcome": "...", "reason": "...", "source": "..."}], "callback_window": {"days_ahead": integer, "day_unit": "business | calendar", "earliest_time": "HH:MM", "latest_time": "HH:MM", "after_now": true | false, "max_outside_asks": integer, "outside_close_value": "intent value with route end", "source": "excerpt"}}
   (what the person who is not the customer may want. route end: the call closes with that outcome and reason, with no tool. A callback that is booked with a tool keeps route stay: the program closes it from the tool result.
   callback_window: when a callback may be booked, copied from the documents; omit it when they set no limit. days_ahead: how many days after today are allowed (0 = today only; "today or the next business day" = 1 with day_unit business). earliest_time/latest_time: the allowed time of day, both included, 24-hour. after_now: true when the time must be later than the call's current time. max_outside_asks: how many times the agent asks for another time after an offer outside the window (0 if the documents do not say). outside_close_value: the intent value (route end) to close with when the next offer is still outside or no clear time is given; required with a window (if the documents name no row for it, the closest no-callback value). The program resolves and checks the person's day and time in code; the model never types the date.)
 "identity": {
  "rules": [RULE] (limits, refusal handling, what never to do before all questions pass),
  "questions": [{"field": "value of the identity tool's question selector enum", "ask": RULE, "answer_format": RULE (how to convert the spoken answer into the tool format)}] (in the order asked),
  "verified_field": "identity tool response field (boolean) that is true when the whole check passed",
  "attempts_left_field": "identity tool response field (integer) with the wrong answers or attempts left",
  "answer_verified_field": "identity tool response field (boolean) for the answer just checked",
  "failed_answer_instruction": RULE (what to do after a failed answer, including any hint the tool returns),
  "exhausted_say": RULE (text: the exact words said to the customer when no attempts are left, word for word, not an instruction such as "Tell the customer ...")
 },
 "global_rules": [RULE] (rules for the whole call: honesty, questions the agent cannot answer, repeated refusals to talk, recording claims, goodbye before the closing tool),
 "sources": {"opening.max_unclear_asks": "excerpt or fallback: why", "opening.forbidden_before_verification": "excerpt"},
 "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]
}
```

## EXTRACT_FLOW_TASK

- Purpose: Extracts the account, negotiation and confirmation sections.
- Receiver: builder model
- Used at: builder/extract.py — extraction call 'flow'
- Approximate tokens: ~776 (characters ÷ 4)

```text
Extract the sections account, negotiation and confirmation. RULE means {"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}.
Date limits, amount limits and the offer limit are extracted elsewhere; here keep only the conversation rules.
Return this JSON shape:
{
 "account": {"rules": [RULE] (how to state the debt and the products, in which order), "products_field": "account tool response field (array) with the late products", "product_id_field": "field of one product item that identifies it for the promise tool", "product_kind_field": "product item field with the kind of product, or """, "product_label_field": "product item field the customer recognises the product by, such as its last digits, or """},
 "negotiation": {"rules": [RULE] (what to ask first, what counts as a refusal, persuasion attempts and what each proposes, what never to offer, per-product handling),
  "intents": [{"value": "snake_case code", "meaning": "...", "route": "readback | end | stay", "outcome": "...", "reason": "...", "per_product": true or false, "uses_attempt": true or false, "source": "..."}]
   (the customer's state after each turn. route readback: an agreed date and amount are ready to read back. end: the customer refuses any arrangement after the allowed attempts; give the closing-table outcome and reason. stay: keep negotiating. At least one readback and one end value. Only refusing to pay or to talk may use route end. per_product true (route end only): the refusal ends only the product being discussed when the documents handle several products one at a time; the call goes on with the next product and closes with this outcome only when no product is left. uses_attempt true (route stay only): a flat refusal or a non-answer that uses one persuasion attempt; code counts these per product when the offer section gives persuasion_attempts. Leave both false when the documents give no such rule. Situations with their own sentence or tool (the payment was already made, the debt is denied, a transfer is requested, financial difficulty) are special paths, extracted elsewhere: never list them here, or the call would close without the sentence or the tool.)},
 "confirmation": {"rules": [RULE] (read-back, explicit confirmation, changes, one promise per product, what to say after a recorded promise, what to do when recording fails),
  "promise_product_id_field": "promise tool request field for the product id",
  "promise_date_field": "promise tool request field for the date",
  "promise_amount_field": "promise tool request field for the amount",
  "max_attempts_per_product": integer (recording attempts per product, the first one included),
  "intents": [{"value": "snake_case code", "meaning": "...", "route": "record | change"}]
   (record: the customer clearly confirmed the read-back. change: the customer wants a different date or amount, or rejects the read-back.)},
 "sources": {"confirmation.max_attempts_per_product": "excerpt or fallback: why"},
 "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]
}
```

## EXTRACT_OFFER_TASK

- Purpose: Extracts the date and amount rules that code uses to check every offer.
- Receiver: builder model
- Used at: builder/extract.py — extraction call 'offer'
- Approximate tokens: ~807 (characters ÷ 4)

```text
Extract the section offer: the calendar, the date limits and the amount limits a promise must meet. Code evaluates them against the call's current date; you only copy the rule data. RULE means {"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}.
Return this JSON shape:
{
 "offer": {
  "rules": [RULE] (date and amount rules the agent must also follow in conversation: vague periods, this/next weekday meaning, what to propose when a date or amount is not allowed),
  "today_variable": "call variable with the current date and time",
  "non_business_weekdays": [ISO weekday numbers, 1 = Monday ... 7 = Sunday],
  "holidays": ["YYYY-MM-DD", every non-business date listed],
  "promise_date_must_be_business_day": true or false,
  "earliest": {"days": integer, "unit": "business | calendar"} (first allowed promise date counted from today; 0 calendar days means today),
  "latest": [{"when": [CONDITION], "days": integer, "unit": "business | calendar"}] (the latest allowed date, counted from today; ordered, the first rule whose conditions match the product applies; omit when for a rule that applies to every product),
  "latest_on_non_business_day": "previous | next | keep" (when a calendar-day latest date is not a business day),
  "min_amount": [{"when": [CONDITION], "field": "product field"} or {"when": [CONDITION], "value": number}, optional "share": fraction of the field or value],
  "max_amount": [same shape as min_amount],
  "next_weekday": "following_week | upcoming | ask" (what "next <weekday>" means. following_week: that weekday in the following calendar week. upcoming: the nearest such weekday after today. Use one of these two only if the documents define "next <weekday>"; otherwise ask, and the agent asks which date is meant),
  "max_rejected_offers": integer, at least 2 (an invalid-offer counter: how many distinct customer offers that fail the date or amount checks above a product may have before it is given up. It is NOT the number of persuasion attempts after a refusal: never copy a persuasion or attempt count here. Use 2 (one invalid offer, then the agent's counter-offer may be rejected once) unless the documents set a limit on invalid or out-of-policy offers; give the source "fallback: no invalid-offer limit in the documents"),
  "max_rejected_offers_by_product": [{"when": [CONDITION], "value": integer, at least 2}] (only if the documents set different invalid-offer limits for different products; otherwise []. Persuasion attempts per band are not invalid-offer limits),
  "persuasion_attempts": [{"when": [CONDITION], "value": integer, at least 1}] (the number of persuasion attempts after a flat refusal, per product, when the documents give it, for example per band; first match wins; [] when the documents give no number)
 },
 CONDITION is {"field": "product field", and one or more of "min": number, "max": number, "equals": value, "in": [values]} (min and max are inclusive). Product fields come from the account tool's product items in the tool contract.
 "sources": {"offer.<field>": "excerpt or fallback: why", one entry per field above},
 "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]
}
```

## EXTRACT_OUTCOMES_TASK

- Purpose: Extracts the closing table, the special paths and the closing tool fields.
- Receiver: builder model
- Used at: builder/extract.py — extraction call 'outcomes'
- Approximate tokens: ~1299 static + `{states}` characters ÷ 4 at runtime

```text
Extract the sections outcomes, special_paths and closing. RULE means {"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}.
Return this JSON shape:
{
 "closing": {"rules": [RULE] (how the call ends; most are enforced_by closing_outcome. An instruction for what the agent does during the call, such as notes or transfers, belongs to the step where it happens, not here), "outcome_field": "closing tool request field for the outcome", "reason_field": "closing tool request field for the reason", "product_notes": null or {"tool": "note tool name", "product_field": "note tool request field for the product id", "reason_field": "note tool request field for the reason", "reasons": ["every reason value the documents allow"], "refused_reason": "reason for a product the customer turned down or never agreed to", "failed_reason": "reason for a product whose promise could not be recorded", "skip_outcomes": ["call outcomes after which no note is added at all, for example a transfer"], "outcome_from_notes": null or {"all_reason": "the note reason that, on every product, gives its own row", "all_outcome": "outcome of that row", "all_outcome_reason": "reason of that row or \"\"", "otherwise_outcome": "outcome used otherwise, with the reason of the first product in account order whose note is another reason", "source": "excerpt"} (only when the documents derive the call outcome from the notes when no promise was recorded; null otherwise), "source": "excerpt"} (only when the documents require a note for each product that ended without a promise; code then writes those notes before the closing tool; null otherwise)},
 "outcomes": [{"outcome": "...", "reason": "... or \"\"", "when": RULE, "say": RULE (text: the exact words the agent says to the customer before the closing tool, word for word, read aloud as written; include every sentence the brief requires in that situation and end with a goodbye. Never an instruction such as "Thank the customer and say goodbye."; write "Thank you for your time. Goodbye." instead), "wins_over_promise": true or false (true only if this row is used even after a promise was recorded), "states": ["call-end state names below that close with this row"]}]
   (one row per outcome and reason pair the brief allows; every pair from the closing table.)
 "special_paths": [{"id": "snake_case", "when": RULE (what the customer says), "say": RULE (text: the exact words said to the customer, read aloud as written; never an instruction to the agent), "ask": RULE (optional; leave the key out unless the documents require one question before acting, for example whether the agent can help first or whether the customer wants to be connected. The agent says it to the customer and waits for the answer, so it must be one question ending with "?", never an instruction), "tool": "tool name or \"\"", "tool_args": {"field": "fixed value"}, "outcome": "...", "reason": "...", "available_in": ["opening | third_party | identity | negotiate | confirm_record"], "then": "close | return"}]
   (situations that interrupt the normal flow, for example: the customer says the payment was already made, denies the debt, reports financial difficulty, asks for a different plan or for a person; or a note on one product. tool_args holds only values the brief fixes; fields the conversation must fill are left out. then close: the call closes with outcome and reason, which must be a row above. then return: the agent goes back to the step it came from (outcome and reason are still required; repeat a row's values). Do not use the identity, account, promise or closing tools here. available_in lists only steps where the situation may happen: never before identity is verified if it would disclose the account.)
 "derived_states": {"state name": "why this row"} (every state below that the documents do not name, with the reason you chose its row; no excerpt needed),
 "sources": {},
 "overrides": [{"newer": "excerpt", "older": "excerpt", "effect": "..."}]
}
Code checks this reply; each failed check costs a repair round:
- Every RULE (when, say, ask) has non-empty text and a source copied word for word from the documents; never "derived" or "fallback" in a rule source.
- Each outcome and reason pair is written together in one row or sentence of the documents, copied exactly; reason is "" only when the documents give none. No pair appears twice.
- Every special path's outcome and reason is one of the rows, also for then return.
- tool_args keys are request fields of that tool; enum fields use an enum value from the tool contract.
- Every state name below appears in exactly one row's states; every required state is mapped.
- An ask is one question ending with "?" and only with then close; otherwise leave the key out.
- Every say and ask is the customer's words, read aloud as written: no "the customer", no instruction to the agent such as "Say ...", "Tell ...", "Offer ..." or "Do not ...".
Call-end states. Map each required state to exactly one row. If the documents do not name a state, map it to the closest row and list it in derived_states. An optional state left out uses the row of "default":
{states}
```

## CLOSE_STATE_GUIDE

- Purpose: Meaning of each fixed call-end state, listed in the outcomes extraction call.
- Receiver: builder model
- Used at: builder/extract.py — {states} in EXTRACT_OUTCOMES_TASK
- Approximate tokens: ~287 (characters ÷ 4)

```text
- opening_unclear (required): who answered stayed unclear after the allowed asks.
- callback_scheduled (required): the callback tool booked a callback.
- callback_failed: a callback could not be booked.
- identity_failed (required): no identity attempts are left.
- promise_recorded (required): at least one promise was recorded.
- promise_failed (required): recording a promise failed on every allowed attempt.
- account_failed (required): the account could not be fetched (a technical failure).
- offer_limit (required): a product's offers kept failing the date and amount checks; usually the refusal row.
- turn_limit: the conversation ran too long without progress.
- special_tool_failed: a special path's tool failed.
- hangup (required): the verified customer ended the call before the closing step.
- hangup_unverified (required): the call ended before identity was verified.
- default (required): the call ends in a way no other state covers, usually no promise.
Route values that end the call (opening answers, third-party intents, negotiation intents with route end) are mapped through their own outcome and reason; do not list them here.
```

## EXTRACT_REPAIR_TEMPLATE

- Purpose: Sends code-validation errors back for one extraction call.
- Receiver: builder model
- Used at: builder/extract.py — repair round (same conversation)
- Approximate tokens: ~40 static + `{errors}` characters ÷ 4 at runtime

```text
Code validation found these problems in your JSON:
{errors}
Fix them using the documents. Change nothing else. Return the complete corrected JSON object, same shape.
```

## COVERAGE_TASK_TEMPLATE

- Purpose: Maps every brief item to the spec path that covers it, or marks it not relevant or missing.
- Receiver: builder model
- Used at: builder/extract.py — coverage call
- Approximate tokens: ~152 static + `{items}` characters ÷ 4 + `{spec}` characters ÷ 4 at runtime

```text
Below are the numbered items of the documents and the extracted spec. For every item decide:
- covered: the spec carries its meaning. Give the spec paths, for example "opening.rules[0]", "offer.holidays" or "special_paths[2]".
- not_relevant: it gives no instruction to the phone agent (titles, background, examples already covered, notes about other documents).
- missing: it is an instruction or value the phone agent needs and no spec path carries it.
Return {"items": [{"id": number, "status": "covered | not_relevant | missing", "paths": ["..."]}]} with every item id exactly once.

# ITEMS
{items}

# SPEC
{spec}
```

## COVERAGE_FOLLOWUP_TEMPLATE

- Purpose: Asks once for spec additions that cover the items the coverage call found missing.
- Receiver: builder model
- Used at: builder/extract.py — targeted coverage re-ask
- Approximate tokens: ~175 static + `{items}` characters ÷ 4 + `{spec}` characters ÷ 4 at runtime

```text
These document items are not covered by the spec below:
{items}

For each item, either add it to the spec or explain why the phone agent does not need it. Return {"additions": [{"items": [ids], "target": "<stage>.rules | global_rules | special_paths | outcomes", "value": RULE or a full special path or outcome row in the spec's shape}], "not_relevant": [{"item": id, "why": "..."}]}. Stages: opening, third_party, identity, account, negotiation, confirmation, offer, closing. RULE means {"text": "...", "source": "verbatim excerpt", "enforced_by": "optional, see RULES THE PROGRAM ALREADY ENFORCES"}. Prefer a short rule in the step where it applies; use global_rules only for whole-call rules.

# SPEC
{spec}
```
