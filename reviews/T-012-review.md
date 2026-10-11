# T-012 review (claude-dev2, more self-check scenario families)

**Reviewer:** claude-reviewer · **Scope:** the T-012 parts of `builder/selfcheck.py` (hang-up, turn limit, account failure, callback answers, revise, two special paths, special path at another step, `end_of_call`, `_compiled`, reach rule `PLAYED_CALL_END_STATES`, `follow`, `spoken_per_turn`), `tests/test_selfcheck_families.py`, the walker moves in `tests/test_multi_step.py` and `tests/test_closing_speech.py`, `tools/submission_check.py`. The T-011 parts (closing, `_notes_pair`) are ignored as asked.
**Method:** offline. Read the code and the generated end-of-call hook of Brief A; `python3 -m unittest`: **518 OK** (23 s). My own mutations of the rendered Brief A workflow (six), a cache test, a duplicate-state test, and two extra hang-up probes. Build-mode self-check of Brief A: 0.07 s. Scratchpad only; no Freya, no model, no env, no edits (only this file).

## Decision: **merge edilebilir** (LOW notes only; no false pass found in the new families)

## Checks

**1. False passes in the new families — none found.** My mutations of the rendered workflow, all caught:

| Mutation | Result |
|---|---|
| hang-up row of the hook table changed to another outcome | `hangup_negotiate` fails |
| hook no longer tries `hangup_unverified` | `hangup_opening`, `hangup_identity` fail |
| hook never sends (URL always empty) | all four hang-up scenarios fail ("0 close calls") |
| hook sends even when the closing chain already closed | `opening_*`, `identity_failed`, `promise` and more fail ("2 close calls") |
| `max_turn_transition` removed from the opening only | `turn_limit_opening` fails |
| (their table) account route, callback keep-day, revise routing, no-way-back, excluded step | caught as listed in the report |

The expectations come from the spec rows (`_hangup_pair`: unverified row, then hang-up row, then default), not from the hook. Every earlier scenario now also checks that the end-of-call hook does not send a second close, which is a real new safety net. A hang-up skips only the "reaches `end_call`" check (the call ends by definition) and keeps the close-count, pair and promise checks.

**2. Compile cache cannot hide a changed workflow.** `_compiled` is `lru_cache` keyed on the **code string itself**; the compiled object is immutable and each `exec` gets a fresh sandbox. I warmed the cache, appended `raise ValueError` to the `closing` code in the same process and re-ran: the scenarios fail; I restored the code: they pass again. A syntax error is not cached (it raises each time and is caught inside the step's `try`). The 1024 entries are enough for one build.

**3. Reach rule for played states.** A row mapped only by `hangup`, `hangup_unverified`, `turn_limit`, `account_failed`, `callback_failed` must now be reached by a **played** scenario; if the scenarios cannot play the state it is a BUILDER note "(state not played)", never a repair, which is right (a gap of the generator is not a spec fault). Rows with other states keep the old rule; the default row is skipped. Two rows claiming the same state are rejected by spec validation before this point (I tried it: `outcomes[6].on repeats state 'hangup'`), so `_hangup_pair`'s "first row with the state" cannot hide a second row.

**4. Walkers.** `follow` is the old `walk` on the self-check's `holds` and sandbox (raises on a code error, a disallowed import or a loop); `spoken_per_turn` and its silent-tool rule moved; the changed T-010 test (`test_a_missing_close_call_is_caught`) correctly excludes the four hang-up scenarios, which close through the end-of-call tool.

**5. `submission_check`.** The line is optional; when present it must match `scenarios=N pass=N fail=N spec=N builder=N` in order with `pass + fail = scenarios`; six malformed forms are tested.

## Findings (all LOW)

1. **Unverified assumption: "an empty URL sends nothing".** The simulator models a hook that skips by setting `config['url'] = ''`. The kit docs do not say what the platform does with an empty URL after a pre-hook. F-012 (live) proves only the *sending* hook; the *skipping* path (normal call end, closing already done) has no live evidence. Add to the live checks: in an ordinary completed chat, the ledger must show exactly one `close_call`. If the platform fails or still posts, the fix is in the hook, not in the self-check.
2. **Hang-up positions not played:** during the third-party step, during the callback question, inside the record loop (after an accepted offer, before the confirmation) and after a partial failure. My probe at the third-party step gives `not_verified/declined` (the unverified hang-up row), which is sensible; the other positions are untested. One scenario per position would complete the family.
3. **Hang-up and turn-limit scenarios use one product,** so "some products already noted by special paths, then hang-up" is not played (see the open question).
4. **`self_check_summary` check:** `spec + builder = fail` is not enforced; add it (the line is generated, so the check is cheap).
5. **Two special paths:** only the first returning path with the first closing path per step; two returning paths in a row stay unplayed (the report says so).

## Open question: no notes after a hang-up — my view

The note rule ("each product that ended without a promise gets a note") cannot run after a hang-up, because only the lifecycle `end_of_call` tools run and the note loop is part of the closing chain. The kit scoring compares the notes **exactly** (`score.py`: sorted note list must equal the expected one), so a hang-up case whose expected ledger contains notes would fail.

My recommendation: **do not build it now; record it as a known risk and ask the organizers.**
- The public set has **no** hang-up case (no "hang", "disconnect" or "cut off" in `public-test-set.json`), and the briefs say nothing about a customer ending the call; the expected ledger of such a hidden case is unknown. The most probable expectation is the close row only (what F-012 already produces); writing notes could just as easily make a case fail.
- It is expensive and fragile: one HTTP call per product means several lifecycle tools (one per possible product index, each hook blanking its URL when not needed), the execution order of `end_of_call` tools is not documented, and the bank mock's behavior for `add_note` after `close_call` is unknown. A generic design would have to guess the number of products.
- If the CTO wants cover anyway, do it as a spec-driven option behind the existing note rule (a flag `notes_on_hangup`, off by default), test it in one practice chat with approval, and keep it off if the ledger shows an unexpected note.
- Action now: add the question to the organizer list ("Is a customer hang-up expected to write per-product notes, or only the close row?"), and keep the scenarios' current rule (no notes checked on a hang-up, except after a promise).

## Live checks (CTO, with approval)

1. A normal completed chat on the Brief A agent: exactly one `close_call` (finding 1).
2. A hang-up chat in negotiation with one product and with several: the single close row; look at the ledger for notes only to document, not to fix.
