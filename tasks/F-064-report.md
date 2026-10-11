# F-064 report

Implemented a generic guard for third-party replies that are questions, offers to pay, or requests for protected information.

## Changes

- Added a catalogued third-party intent extraction description. Spec-defined closing values may now be selected only for an explicit refusal or a clear statement that the customer cannot be reached; questions, payment offers, and information requests select the framework `none` value.
- Added an independent builder-owned `explicit_close | other` extraction signal. This lets code verify a closing intent instead of trusting the intent label alone.
- Routed spec-defined third-party closing intents through `third_party_close_check`. An explicit close proceeds immediately. A first non-explicit close is reset safely, produces one fixed no-disclosure callback-time question, and increments a counter; a repeated close proceeds so the workflow cannot loop indefinitely.
- Reused the existing `third_party_ask` node and `callback_message` path, keeping the behavior consistent with the bounded callback-check flow. Enum resets use valid values rather than an empty string.
- Added tests for the live F-064 sentence, the bounded second attempt, and the explicit refusal “she doesn't want to be called”. Updated terminal-path fixtures to carry the new explicit-close signal.
- Regenerated `docs/PROMPTS.md` from `builder/prompts.py`.

No brief-specific value was added to builder code or prompts.

## Verification

- `python3 -m unittest tests.test_callback -v` — 41 tests passed.
- `python3 -m unittest` — 385 tests passed.
- `git diff --check` — passed.

No Freya request, commit, or `env.sh` access was made.

## Fix

Applied the required findings from `reviews/F-064-review.md`:

- Both extraction descriptions now receive the spec's own `third_party.close_values`. They classify a clear situation named by any closing value as `explicit_close`, so cases such as wrong number or deceased can close on the first turn; questions, payment offers, information requests, vague replies, and non-answers remain `other`.
- Render tests cover Brief A, the cumulative A+B fixture, and the synthetic fixture, and assert that every spec-defined closing value appears in both extraction descriptions.
- The guard now resets `third_party_close_kind` to the valid `other` value on `close_now` and on a non-closing intent. A stale `explicit_close` on a non-closing reply passes through the guard and returns to the third-party conversation; callback date/time routing clears the stale value in `callback_check` as well.
- Added a stateful `ThirdPartySession` route walker. It proves explicit refusal reaches `closing`, a second non-explicit closing intent reaches `closing` after the one bounded re-ask, deceased reaches `closing` on its first turn, and a stale explicit kind on a non-closing reply is cleared before returning to `third_party`.

Review finding 2 is an intentional bounded fallback: if extraction produces a closing intent twice, the second occurrence closes even when its independent kind remains `other`. This prevents an unbounded loop, so repeated questions or payment offers can receive at most one fixed re-ask before the spec-defined close proceeds.

Review finding 4 is unchanged: the fixed re-ask is English, consistent with the project's other fixed lines. Supporting a hidden brief in another language is a project-wide localization concern rather than an F-064-specific change.

`docs/PROMPTS.md` was regenerated. Offline verification after the fix: `python3 -m unittest tests.test_callback -v` passed 44 tests, and `python3 -m unittest` passed 394 tests. No Freya request, commit, or `env.sh` access was made.

## Fix 2

Applied the F-064 re-review routing fix:

- Removed the stale-kind transition from `third_party`; it could be merged ahead of the callback transition and intercept a complete callback request.
- `third_party_close_check` is now reached only for spec-defined closing intents. Its guard therefore handles only those closing values, with the existing one-re-ask bound.
- Kept `third_party_close_kind` reset to `other` at the two consuming code paths: `callback_check` and `third_party_close_check`.
- Added a stateful route-walk test proving that callback intent + day + time + stale `explicit_close` follows `third_party -> callback_check -> callback_book` in the same turn, resolves the callback date/time, and clears the stale kind.

The concurrent T-009d budget-stage work in `workflow.py` was left untouched. Final offline verification is recorded below. No Freya request, commit, or `env.sh` access was made.

Verification after Fix 2:

- `python3 -m unittest tests.test_callback -v` — 44 tests passed.
- `python3 -m unittest` — 397 tests ran; 394 passed and 3 concurrent T-009d prompt-budget tests failed (`tests.test_prompt_budget`: two `negotiate` budget assertions and one placement-note assertion). No F-064 test failed, and those failures were not changed because T-009d is owned by `claude-dev2`.
- `git diff --check` — passed.
