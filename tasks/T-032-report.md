# T-032 report: review fixes MEDIUM 3, MEDIUM 4, LOW 1, LOW 2

**Owner:** claude (claude-dev2 role). **Source:** `tasks/T-029-030-review.md`. **UAT:** F-091 to F-094.
**Not done:** no Freya request, no model call, no commit, no env.sh. Generic: no brief value in `builder/`, and the leak test is green.
**In parallel:** claude-dev did T-031 (HIGH 1, HIGH 2, MEDIUM 5) in `offer_check.py`, `goodbye_code`, `product_notes.py` and `selfcheck.py`. I did not edit those parts.

## MEDIUM 3: bare thanks and a "no" are not goodbyes (F-091)

This change is in `builder/prompts.py`.

**`CUSTOMER_ENDS_CALL_INTENT`** (the global goodbye step, also listed in each step's special-topic value):
- **Before:** "The customer only says goodbye or thanks to end the call: …"
- **After:** "The customer clearly takes leave (goodbye, bye, or that they are done) and says nothing else: not an answer to a question, no refusal, no offer and no question. "Thanks", "okay" or "yes" alone is not a goodbye."

**`GOODBYE_CHOICE_DESCRIPTION`** (the `ends_call` value of the global ask steps):
- **Before:** "… the customer only says goodbye or thanks to end the call, not an answer to the question."
- **After:** "… the customer only takes leave (goodbye, or that they are done) and gives no answer; "thanks", "okay" or "yes" alone is not ends_call, and a "no" (also "no thanks, goodbye") answers the question."

The "no" answer goes to the step's own decline value (`stay`, or the declined row where the spec has one). The prompt does not name that value, because its name differs from one step to another.

**Budget:** these texts are extraction and routing descriptions, not step prompts, so `negotiate` does not change (brief-ab-extracted-v2 is still 1699 without side questions, under the 1700 guard).

## MEDIUM 4: identity counts distinct questions (F-092)

This change is in `builder/workflow.py`.

- **New pre-hook `identity_asked_hook(fields)`:** it finds the request value that names one of the spec's question fields and stores it in `identity_answer_field`. The fields come from `spec.identity_questions[].field`, so the hook holds no brief value.
- **`identity_pass_hook(verified, answer, fields)`:**
  - `identity_answers_passed` is now a list of distinct fields, joined with commas, instead of a count.
  - The overall field is set only when the bank sent none and every question field is in the list.
  - A call whose question the hook cannot name is not counted.
  - After each call, the hook clears `identity_answer_field`.
- **Unchanged:** the bank's own overall field always wins.

## LOW 1: recording notice grammar (F-093)

This change is in `builder/spoken.py`, in `present_recording_notice`.

- **When it rewrites:** only when the clause ends the thought: end of sentence, a comma or ";" or ":", or a purpose ("for", "to", "so that").
  - "Calls are recorded **and monitored** …" is left as it is, with the warning "left in the line …, the notice clause goes on after 'recorded'".
  - "Your call is recorded so that we can help you." becomes "We are recording this call so that we can help you."
- **"may / might / can be recorded":** now matched as the notice but never rewritten, because the present tense would change its meaning. The build gets the warning "'recorded' is left in the line because the notice says 'may be' recorded …".

## LOW 2: a side question does not repeat the read-back (F-094)

This change is in the new module `builder/readback_resume.py`, plus `READBACK_RESUME_LINE` in `prompts.py` and the wiring in `workflow.py`.

**What changed:**
- **New step `confirm_record_resume`:** a copy of `confirm_record` with the same prompt, extraction and routes. Its fixed line is only "Shall I go ahead with the payments I read out?"
- **Return path:** a global step that can start at the read-back and returns with `__previous__` now first goes to the copy when `readback_reply` holds the special-topic value. That value is how the read-back step sends the call to a side question.
  - It applies to deterministic returns only (a fixed line, or a declined offer of help).
  - An intent return keeps `__previous__`.
- **Fresh entries are unchanged:** an accepted or revised offer, a goodbye read-back, and the end of a special path all still go to `confirm_record`, which says the full read-back.
- **Registered as a read-back step:** the copy is in `STEP_ALIASES` and `STEP_NODES`, so special paths, side-question lines and the goodbye exit apply to it too.
  - It is created before `add_goodbye_exit`, which claude-dev asked for. `goodbye_exit_gaps` is empty on every fixture.
- **Removed when unused:** if no side question returns to the copy (spec-synthetic, for example), the copy and its per-source entry steps are removed.

**Why not `on_enter_first_entry_only`, which the review suggested:** it would also silence the fresh entries (a revised offer, the goodbye read-back). A single tts passthrough step before the read-back was not used either: tts on passthrough steps broke a live turn before (F-050).

**Budget:** the copy has the same prompt as `confirm_record` (935 on brief-ab-extracted-v2, 1059 at most on the fixtures).

## Tests

**New `tests/test_t032_review_fixes.py` (5 tests):**
- the goodbye wording;
- the wording in the rendered steps;
- the read-back copy: its line, routes and extraction, and on every global return the choice of `__previous__` against the copy;
- fresh entries still say the read-back;
- no goodbye gap on any fixture, and an unused copy is removed.

**Changed tests:**
- `tests/test_global_exit_identity.py`: the hook runs pre and post, and there is a new test where the same question three times does not pass and an unnamed question is not counted.
- `tests/test_recording_notice.py`: two new tests, for a clause that goes on and for "may be".
- `tests/test_multi_step.py`: the special-path sources include the copy, and only existing steps are compared.
- `tests/test_side_questions.py`: the copy lists the side questions.
- `tests/test_goodbye_every_step.py:68` (claude-dev's file): one wording line.

**Docs:** `docs/PROMPTS.md` regenerated.

**`python3 -m unittest` on the shared tree with T-031 and T-032:** **644 tests, OK**, including the leak test and the prompt budget guard. claude-dev re-pinned the Brief A render to `c6e4cfe2…` after both tasks were in. `docs/PROMPTS.md` is current.

## Open

- Live checks 3 and 4 of the review: "No thanks, goodbye" at the support offer, and "Okay, thank you" in the middle of the offer talk. These need a chat run with approval.
- A chat run with a side question at the read-back, to confirm that the return goes to the copy. A global step that routes to a normal step on a condition (instead of `__previous__`) is used here for the first time.
