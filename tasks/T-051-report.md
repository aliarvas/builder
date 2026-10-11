# T-051: the generic build stalled on the design call (read timeout)

**Constraints and tests:** no commit, no env.sh, no Freya. `python3 -m unittest`: **712 OK** (4 new tests).

**Live failure (`traces/final.failed.log`):**
- the contract was fine (56 s, 10.9k output tokens, 7 paths);
- `generic:design` was not streamed, with a 600 s timeout plus one retry: 20 minutes lost.

## Changes

1. **Streaming (`builder/llm.py`):** `AnthropicClient(stream=True)`.
   - It sends `"stream": true` and reads the server-sent events with the standard library (`_read_stream`): text deltas, usage from `message_start` and `message_delta`, and `stop_reason`.
   - It returns the same `LLMResult`, so callers do not change.
   - The default stays `stream=False`, so collections mode is unchanged.
   - **Generic mode:** `stream=True` and `timeout=120` (`GENERIC_READ_TIMEOUT_SECONDS`). The timeout is now per silent gap between chunks, not per reply. `max_tokens` stays at 48000.
2. **Smaller design:**
   - The design prompt now asks for at most about 6000 tokens: short phrases, required sentences once, no copied document text.
   - The render prompt asks for task messages "as short as their rules allow".
   - **New flag `--no-design`:** it skips the design call and renders straight from the documents (contract → render).
3. **Tool timeouts:** `clean()` sets `config.timeoutMs` to at least **30000** on every api tool (`TOOL_TIMEOUT_MS`), because one test answer of `cards.balance` waits 12 s. This is applied deterministically, not left to the model; the platform rules in the prompt say it too.
4. **Mock URL with a path:** `base_url()`. If the mock URL is given with the services' common prefix (`…workers.dev/voice/v1/` while the contract paths are `/voice/v1/...`), the prefix is dropped, so tools do not call `/voice/v1/voice/v1/...`. Both forms of the mock URL now give the same tool URLs.

## Recommendation: keep the design step (default)

- **Measured live:** about 195 output tokens per second (contract: 10.9k tokens in 56 s).
- **Estimate with streaming:** a ~6k-token design takes about 30–45 s, and a ~30k-token render about 2.5–3 min.
- **Why keep it:** the design costs well under a minute and gives the render a plan.
- **When to use `--no-design`:** if the design call fails again.

## Command

```bash
python3 builder/build.py --slot final ~/Desktop/final-case/case https://freya-final-mock.cf-smoke.workers.dev
# fallback: add --no-design
```

## Tests (in `tests/test_t046_generic.py`)

- a streamed reply read whole, with the stream flag and a 120 s timeout;
- `base_url` with and without the prefix;
- 30 s tool timeouts after `clean`;
- `design=False` makes only the contract and render calls.
