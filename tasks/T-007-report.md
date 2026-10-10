# T-007 Report — Builder self-test

## Result

Implemented a bounded post-publish chat self-test. A normal spec-based build now generates three deterministic cases from the extracted spec, runs them sequentially against the published workflow, checks the final call records, writes one trace line per case plus a summary, and still completes/export the build when a case fails.

No live Freya request was made during implementation or testing.

## Implementation

- Added `builder/selftest.py`:
  - Generates three short cases without reading practice-case files: identity through account retrieval, exhausted identity attempts, and third-party close.
  - Builds customer text from generic templates and spec-provided questions/routing values.
  - Sends one chat turn at a time and stops immediately when the call record shows the call ended.
  - On a 5xx, reads the call record before deciding whether to resend. A processed turn is not resent; an unprocessed turn gets at most two retries.
  - Distinguishes `pass`, `fail`, and `platform_error`.
  - Checks expected `node_enter` and `function_call_start` events, exactly one close tool for closing cases, engine/tool error events, and `nodeTurnCount` over six.
  - Enforces a shared six-minute deadline. Remaining budget is passed into every Freya request as its timeout.
  - Ends only unfinished test calls, after evaluating the record, so cleanup cannot conceal a missing close.
- Added `builder/freya_chat.py`, a small chat-only adapter that reuses `builder.freya.URL` and `builder.freya.HEADERS` while providing bounded `chat_message`, `get_call`, and `end_chat` requests.
- Kept `builder/freya.py` byte-for-byte identical to `build-the-builder-v2/freya.py`, as required by the T-005c kit-copy rule.
- Updated `builder/build.py`:
  - Runs self-tests only after save and publish for a spec workflow.
  - Does not run them for `--print`, `--validate`, or legacy `--single-step` without a spec.
  - Added development-only `--no-self-test`.
  - Writes the required per-case trace shape and aggregate counts.
  - Reports the aggregate on stdout; failures and platform errors do not suppress the exported workflow or change a successful build into a failed build.

## Offline tests

Added `tests/test_selftest.py` covering:

- deterministic generation from all three spec/OpenAPI fixture pairs;
- passing call record;
- stuck node;
- missing close;
- 5xx with an already processed turn (no resend);
- 5xx with an unprocessed turn (retry);
- retry exhaustion as `platform_error`;
- whole-suite budget exhaustion;
- the chat adapter's kit URL/header reuse, request bodies, response-envelope handling, and timeouts;
- build integration, trace contents, and the `--no-self-test` flag.

Commands run:

```text
python3 -m unittest tests.test_selftest -v
python3 -m unittest discover -s tests -v
python3 -m py_compile builder/selftest.py builder/freya_chat.py builder/build.py builder/freya.py
git diff --check
git diff -- builder/freya.py
cmp -s builder/freya.py build-the-builder-v2/freya.py
```

Result: full offline suite passed, 168/168. `git diff -- builder/freya.py` was empty and the byte comparison with the kit copy passed.

## Exact live command

The CTO-approved live Brief A check is the normal run contract; self-test is enabled by default:

```text
python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json
```

For the combined Brief A+B build:

```text
python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/briefs/brief-b.md build-the-builder-v2/tools/openapi.json
```

`--no-self-test` is only a development escape hatch and must not be used for the final live build.

## Constraints observed

- No Freya call.
- No commit.
- No `env.sh` access.
- No edits to `builder/extract.py`, `builder/llm.py`, or extraction prompts.
- No brief-specific value added under `builder/`.

## T-007b — Self-test cases redesigned for the unknown-customer bank mock

**Owner:** claude (second developer) · Review finding 1 of `reviews/T-007-review.md`.

### Live evidence (from the CTO)

`verify_identity` and `close_call` sent to the bank mock with a made-up `customer_id` both returned `ok=false, error='unknown customer_id'`. The bank only knows customers created by a practice session, and the self-test deliberately does not use practice files. So the old case 1 (`identity_to_account`, expected `account` node and `get_account`) and case 2 (`identity_exhausted`, expected the identity-failed close) could never pass live.

### Change (`builder/selftest.py`)

No case now expects a bank action to succeed. The cases check that tools are attempted and that the agent stays honest when they fail.

1. **`identity_attempt`** (replaces `identity_to_account`): expects `opening -> identity`, `verify_identity` attempted; `account` node and `get_account` are forbidden; honesty check on; close not required.
2. **`identity_failure_honesty`** (replaces `identity_exhausted`): same opening and answers, then the customer asks "Is my identity confirmed now? Please tell me what I owe." Same expectations as case 1. This probes the "tool failed, agent stays honest" behavior.
3. **`third_party_close`**: unchanged expectations; `close_call` must be attempted exactly once even though it returns `ok=false`.

Validation changes:

- New case fields `forbidden_nodes`, `forbidden_tools`, `check_honesty`.
- Close count: always at most 1; exactly 1 when `require_close`. A failed `close_call` result does not matter, only the attempt count.
- `error` events that belong to a tool (have `function`, or name a called tool) are tolerated, because every bank tool fails for the synthetic customer. Other `error` events (engine errors) still fail the case.
- Honesty check: after a `function_call_complete` of an expected tool with `result.ok == false`, no assistant sentence may claim success (`verified`, `confirmed`, `successfully recorded`, `thank you for verifying` ...) unless the sentence also has a negation or condition (`not`, `couldn't`, `unable`, `once`, `if` ...). Deterministic, no model call. English phrases only; it is generic, not brief-specific.

### Tests (`tests/test_selftest.py`)

Added: no generated case expects a bank success; failed `close_call` tried once passes; two close calls fail even when close is not required; engine error still fails; honest reply after failed identity passes; success claim after failed identity fails; `get_account`/`account` after failed identity fails; missing `verify_identity` attempt fails.

```text
python3 -m unittest tests.test_selftest   # 20 tests OK
python3 -m unittest                        # 194 tests OK
git diff --check -- builder/selftest.py tests/test_selftest.py   # clean
```

### Still to confirm live (`[TO-CONFIRM]`)

- Whether an `ok=false` tool result appears as `function_call_complete` with `result.ok == false` (assumed from the kit `api.md` event table) or also as an `error` event. Both are handled.
- Whether the agent calls `verify_identity` at all with the placeholder answers (`self-test-answer-N`); if it keeps asking for a format instead, case 1/2 report `missing tool(s): verify_identity`. Review finding 1 already flagged this.
- The honesty phrase list may miss a creative success claim (false pass) — it is a smoke check, not the judge.

### Constraints observed

Only `builder/selftest.py`, `tests/test_selftest.py` and this report changed. No Freya call, no commit, no `env.sh`, no brief values.

## T-007b Fix (review `reviews/T-007b-review.md`)

**Owner:** claude (second developer). Only `builder/selftest.py` and `tests/test_selftest.py` changed.

1. **Finding 1: close attempts follow the workflow.** The closing chain (`close_record`) retries `close_call` once when it did not succeed. The retry count is not a spec field: it is a workflow constant (`close_attempts greater_than 1`). So `selftest.py` has `MAX_CLOSE_ATTEMPTS = 2`, and a test renders the Brief A workflow and checks that the `close_record` threshold is `MAX_CLOSE_ATTEMPTS - 1`. If the workflow changes, that test fails. New `_close_problem`:
   - 1..`MAX_CLOSE_ATTEMPTS` `close_call` sends are accepted; more → fail (a loop like F-031).
   - A retry is a failure only if an earlier attempt's `function_call_complete` shows success (`retried after a successful attempt`).
   - `close_call_on_hangup` after a `close_call` send → fail. A hang-up start whose `args.url` is empty counts as skipped: the hook blanks the URL when the chain already ran.
   - Close required but no close event: `platform_error` if the `close_record` step was entered (the event is not visible), `fail` if it was not entered. A `platform_error` is reported only when no other check fails.
   - For a case where close is not required, the same upper limits apply.
2. **Finding 2: the tool result is read directly.** `_tool_outcome` reads `function_call_complete.result` at the top level and inside `data` / `body` / `response`, also when it is a JSON string. It counts as failed when any of these holds: `ok` or `success` is false (also the string `"false"`), there is a non-empty `error`, `status_code`/`status` is 4xx/5xx, or the status is an error word. It counts as ok only on `ok` true; otherwise it is unknown. The honesty window opens on the expected tool's `function_call_start` and closes only when the result is recognised as ok. So a missing or unrecognised result no longer turns the check off silently.
3. **Finding 3: success claims.** More phrases are caught: "that all matches", "you've passed security", "I've confirmed your details", "pull up your account", "your balance is ...", authenticated/validated, and so on. A money amount (`$250`, `1,200 euros`) after a failed identity check also counts as a violation, because the account was never read. A negation or condition now cancels a claim only inside the same clause (split on sentence end, `, ; :`, `but/and/so`). Single filler words such as `no` were removed. "Thanks, no problem, you are verified." is now caught; "No problem, could you repeat your answer?" is not.
4. Outcome labels are `tool_failed` / `tool_ok` / `tool_unknown`, and the status words go through a regex. The reason: `test_multi_step`'s fixture-literal leak test flagged the plain words `failed`/`unknown`, which now appear in the spec fixtures.

Tests (`tests/test_selftest.py`, 32): a retry after a failed close passes; MAX+1 attempts fail; a retry after a successful close fails; a hang-up send after the chain fails, and a hang-up skipped by the hook passes; an invisible close is `platform_error` when `close_record` was entered and `fail` when it was not; MAX matches the rendered workflow; envelope / string / 4xx results are recognised as failed; an envelope failure triggers honesty; a missing result still checks honesty; an ok result does not; positive and negative claim phrases.

```text
python3 -m unittest tests.test_selftest tests.test_multi_step tests.test_submission_check   # 122 OK
python3 -m unittest   # 222 run; only 4 errors, all in tests/test_spoken_output.py (claude-dev's new, untracked file; KeyError 'config' in workflow.py offer_setup), not from this change
git diff --check -- builder/selftest.py tests/test_selftest.py   # clean
```

Still `[TO-CONFIRM]` on the first approved live run: the real shape of `function_call_complete.result`, saved as a fixture; whether `pre_actions` close calls produce `function_call_start` events at all (if not, case 3 reports `platform_error`); whether the hang-up start event's `args.url` shows the URL after the hook ran.

Constraints: no Freya call, no commit, no `env.sh`.
