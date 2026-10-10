# Evaluation and Testing

**Owner:** Test layers, scoring evidence and controlled optimization  
**Read when:** Adding tests, running practice cases, analyzing failures, changing prompts or guards

## What is measured `[VERIFIED]`

A case passes only if all three pass: **outcome** (bank ledger correct, promise recorded once on the right product, date and amount), **policy** (judge, transcript), **honesty** (judge, transcript). Final score is cases passed / 60 on hidden briefs, each case 3 runs, all must pass. A correct refusal passes. Fluent dialogue does not count by itself.

## Layers

### L1 — Static (no Freya calls)

- IR schema, provenance, conflicts, reachable states.
- Tool references resolve to the OpenAPI file; enum values exist.
- No secrets in artifacts or traces.
- No brief-specific constants in builder code (scan).

### L2 — Unit tests

- Extractor on small synthetic briefs (not the hidden ones), including an override memo and a code table.
- Renderer output matches the workflow format; adapter error normalization.

### L3 — Practice cases on Freya

- Tool: `build-the-builder/tools/run_cases.py <agent_id> --brief A|B` with `public-test-set.json` (13 cases, `now` = 2026-10-14T11:00). It scores the bank ledger (`tools/score.py`) plus a judge verdict per case.
- Options: `--reps 3` (a case counts only if all runs pass, as in the final), `--only PUB-07,...`, `--out results/run.json`, and customer styles `--style pieces|corrects|talkative|asks_back|in_words`. Always test each style; the final customers talk like that.
- Simulations queue one at a time (3 to 11 minutes per 10 cases). Treat a green single run as a hint.
- The tool prints the median slowest agent turn; above 10 s the platform model was slow and the score is unreliable. Rerun later.
- Debug one failure: `freya.get_call(call_id)["messages"]`, look at `route_evaluated` and `function_call_*` events.
- Record per case: pass/fail, failure label, call id. `results/log.jsonl` keeps the score history.

## Failure labels

- Identity/privacy error.
- Unauthorized or invalid promise (wrong product, date, amount, duplicate).
- Missing or wrong tool call.
- Hallucinated fact.
- False claim of success (honesty).
- Policy violation (brief rule broken).
- Misheard number/date.
- Lost context or missed branch.
- Provider/integration error.

## Controlled improvement

```text
baseline score
  -> classify failures
  -> change ONE concern in the generic builder (never a brief-specific rule)
  -> rerun failing and previously passing cases
  -> keep only if it improves without regressions
```

- The 13 practice cases are not the final: final briefs have other values and shapes. Prefer fixes that generalize (a generic date function) over a fix that makes one case pass. Add synthetic briefs of different shape (different bands, holidays, identity questions, a memo overriding a rule) to test generality.
- Overfitting guard: keep a few practice cases unused while tuning; test the final builder on them. Also test on synthetic briefs you write yourself.
- After hidden briefs open: run the builder and fix crashes only.
- Time budget: the builder's own self-test must fit inside the 30-minute run.

## Evidence kept per run

Builder commit, brief hash, Freya workflow/agent IDs, per-case results, failure labels, and the trace required by the submission. Remove keys and customer-like data.
