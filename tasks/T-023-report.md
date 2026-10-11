# T-023 report: special paths behind step routes (PUB-08) and the answer to a path's question (PUB-05)

**Owner:** claude (claude-dev2 role) · **Input:** `tasks/T-021-report.md`.
**Not done:** no Freya request, no model call, no commit, no env.sh.
Everything is generic: no brief value in `builder/`, and the leak test is green.

## 1. PUB-08: a forced choice hid the special path

**Cause (T-021):** the platform tries a step's own routes before the special paths' intents and stops at the first match. The step's choice field had no value for "something else", so "I paid it in the app this morning" became a refusal, and `special_already_paid` was never tried.

### Render (`builder/workflow.py`, `_add_special_topic`)
- **New value.** Every conversation step where special paths start by intent gets a new value, `special_topic`, in its choice field. The choice fields are `choice_variables(spec)`: who answered, the negotiation intent, the read-back intent and the third party's intent.
  - The value is placed before `none`, which stays last as the system value.
  - No step route matches it, so the platform goes on to the intents.
- **Description.** The prompt `SPECIAL_TOPIC_DESCRIPTION` adds one sentence to the field's description: "special_topic: the customer's message is about one of these: <when 1>; <when 2>; … Choose special_topic instead of any other value, also a refusal, an agreement or unclear."
  - Only the paths that can start at that step are named. At the opening that means human, robot and scam, not already paid.
  - "Unclear" is named because at the opening "unclear" also covers "a question back", which would take the robot and scam questions.
- **Covered steps:**
  - Brief A fixture: `negotiate`, `offer_say`, `revise_ask`, `confirm_record`.
  - A+B v2: also `opening`, `opening_reask`, `third_party`, `third_party_ask`.
  - `identity` routes on tool results, not on a choice field, so it needs nothing.
- **Prompt budget:**
  - The step prompts (task messages) are unchanged; only extraction field descriptions grow. The T-009 budget counts the step prompts only.
  - The negotiate description grows by about 600 characters (8 situations) in A+B and about 250 in Brief A.

### Self-check (`builder/selfcheck.py`)
- **Platform order:** `Simulator.intent_turn(extracted, node)`.
  - The turn writes the step's fields and the step routes first.
  - Only when no step route holds does the special path start.
  - It returns "step", "special" or "" (nothing moved).
- **New family `special_<id>_over_choice_at_<step>` (`_competing_label_scenarios`):**
  - **Which paths:**
    - every closing special path at `negotiate`, `confirm_record` and `opening`;
    - every returning path at `negotiate` (A+B: `already_paid` and `dispute` write a note and go on).
  - **The turn** carries the closest refusal:
    - negotiate: the product-end or close value;
    - read-back: the revise value;
    - opening: the close value.
  - **The `special_topic` value instead:** at play time the turn carries `special_topic` when the step's field offers it and its description names this path's situation, because the extraction follows the description (`_topic_choice`).
  - **Expected ledger:**
    - for a closing path, its pair and notes (`_closing_case`);
    - for a returning path, its note, then a refusal (as in `_special_scenarios`).
- **Static check `shadowed_intent_steps(spec, workflow)`:** for each conversation step where an intent path starts and a choice field is routed, the field must have `special_topic`, no step route may take it, and every situation must be named.
  - `run_selfcheck` reports each problem as a BUILDER result `intent_shadow[<step>]`, which goes to the trace and is not a repair.
  - On a render shape it does not know, it reports "check failed" and never raises.
- **Generated scenarios per spec:**

  | Spec | Scenarios | Paths covered |
  |---|---|---|
  | Brief A fixture | 7 | already_paid, dispute, human × 2–3 steps |
  | A+B v2 | 11 | — |

  The family passes on all 10 fixture specs, and the static check finds nothing on today's render.

### Mutation (the version 18 render)
With `special_topic` removed from every field:
- **All** of the family's scenarios fail, on Brief A and A+B. Example: "at negotiate the step's own route takes the turn {'negotiation_reply': 'refuses_after_attempts'}, so special_hardship_support never starts". The ledger then shows `no_promise/refused` instead of the path's pair, as PUB-08 did live.
- The static check flags `negotiate`, `offer_say`, `revise_ask`, `confirm_record` and `opening`.
- A step route that takes `special_topic` is caught ("a step route takes"), and so is a situation missing from the description ("not named"). The latter also makes the family's turn fall back to the refusal, which then fails.

## 2. PUB-05: the answer to "connect you to support?"

### Wording (`SPECIAL_CHOICE_DESCRIPTION`)
- **The problem:** a "yes" to the question can mean either way.
  - "Would you like me to connect you…?" yes = go ahead.
  - "Can I help you with something first?" yes = don't transfer.
- **The new wording** therefore says what going ahead does, taken from the path itself, not yes or no: "The agent asked: "<ask>" proceed: the customer wants the agent to go ahead now and call transfer_to_agent (queue support). stay: the customer does not want that, or wants to go on with the call. Judge by what the customer wants done, not by the word yes or no."
- **The action text (`_path_action`)** is the tool with its fixed values, or the path's line for a path without a tool.
- **Readings:**
  - **`human_request` stays correct:** "No, just put me through" means it wants the transfer (proceed); "Yes, you can help" means stay.
  - **PUB-05:** "I do not want to be transferred" does not want the transfer, so it is stay.
- The old wording ("still insists on this request") is gone. Transition texts: "The customer wants this" / "The customer does not want this".

### Optional `on_decline` (spec schema)
- **`SpecialPath.on_decline`** is the id of the closing path for a no. It is optional, and the default `""` keeps today's behaviour (back to the step).
- **`parse_spec`** requires the path to have `ask`, and the target to be another path with `then: close` and no `ask`; otherwise it raises `SpecError`.
- **Extraction:**
  - the outcomes prompt asks for it as an optional key ("the closing path the documents give when the customer does not want what this path does after the question");
  - `_check_outcomes` asks for a repair when it is wrong, and in the last round only warns;
  - `merge_groups` drops an `on_decline` it cannot use. So a bad value never fails a build; a no then goes back as before.
- **Render:**
  - with `on_decline`, `stay` routes to a new plain step `special_<id>_declined`: the target path's own step, without the intent condition. It writes `special:<target>`, so `closing` gives that path's pair and line.
  - Targets whose tool needs a value from the conversation are not supported, so `stay` keeps going back.
- **Self-check:**
  - new scenario `special_<id>_declined` (`_decline_scenarios`): the customer says no to the question, and the ledger must be the target's pair. In A+B with the link that is `no_promise/hardship` with its note;
  - an ask-first path with `on_decline` is no longer used as the "returning" path in the two-special family;
  - `_inside_special` picks the answer by its operand (`proceed`/`stay`). Spoken-only paths keep their empty turn.
- **Mutation:** routing `stay` back to `__previous__` (the version 18 behaviour) is caught by `special_hardship_support_declined`.
- **The existing fixtures have no `on_decline`** (they were extracted before this field). So until the next extraction the hardship no still goes back to `negotiate`, where the global `hardship_declined` intent can close it. The wording fix works without the field.

## Tests

**`tests/test_special_topic.py`** (13 tests):
- render: the value, its place before `none`, the named situations per step, no value where no intent path starts;
- the family on every fixture;
- the version 18 mutation on Brief A and A+B (family + static check + the `intent_shadow` result in `run_selfcheck`);
- a route that takes the value; a missing situation; the platform order (the step's route takes the turn, the path never starts);
- the choice wording for both ask paths;
- without `on_decline` a no goes back; with it, the no closes as `no_promise/hardship` and no hardship scenario fails; the version 18 routing is caught;
- `parse_spec` rejects bad targets; `merge_groups` keeps a good `on_decline` and drops a bad one.

**Render pin:** `test_brief_a_renders_byte_identically` was re-pinned (`db9effa1…`).
- With my render changes switched off in a scratch copy, the hash is `88408e…`, still not the old pin: claude-dev's T-022 work in the same tree moves it too.
- My part of the Brief A diff is only the choice fields and descriptions of 4 steps and the human-request question's wording.
- When T-022 is finished, the pin must be set once more.

**`python3 -m unittest`: 574 OK.**
- During claude-dev's edits, failures came and went (offer tests, `docs/PROMPTS.md`, the leak test); the final run is green.
- `git diff --check` reports one blank line at the end of `builder/selfcheck.py`. It comes from T-022's `spoken_date` family at the end of the file, which is not mine; I left it so as not to touch their part.

## Open

- **The sympathy line comes after the transfer.** For `hardship_support` the sympathy sentence (`say`) is still spoken only at the close, so after the transfer. This was "smaller" in T-021 and not part of this task.
- **Risk of the new value:** the extraction may choose `special_topic` for a real refusal that mentions money trouble. No intent then matches, so the step keeps waiting and the agent asks again. That costs one turn, and the turn limit stays the bound.
- **Needs live confirmation:** a chat run (with approval) of PUB-05 and PUB-08 on both styles. The platform order is taken from the version 18 traces (step routes first, intents only when none holds).
- **Recommended:** re-extract Brief A so that `on_decline` is filled from rule 32.
