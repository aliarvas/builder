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
