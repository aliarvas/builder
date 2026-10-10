# T-006b — Messy and changed briefs for extraction rehearsal

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

One hidden brief will be "raw bank material" (mail, policy extract, a memo that changes the policy, a code list), the other a clean spec. Fields and allowed values may differ. We must rehearse extraction on inputs we did not tune for. See `docs/SELF-TEST.md` step 2.

## Deliverables (test data only, never under `builder/`)

Under `tests/briefs/`:

1. `raw-a/`: Brief A rewritten as raw material, same rules: an email thread from a manager, a policy extract with numbered clauses, a later memo that **changes** two rules (e.g. a deadline and an identity question), a CSV-like outcome code list, a holiday list written in a non-ISO format. Keep a small `expected.md` that lists the effective rules after the memo, written by hand.
2. `changed-a/`: Brief A with different numbers, identity questions, outcome/reason table, calendar, bands and persuasion attempts, same structure. Plus `openapi-changed-a.json`: kit OpenAPI with changed field names where the brief allows it (e.g. identity field enum values, close_call enums, transfer queues). Tool names stay the same.
3. `tests/briefs/README.md`: how to run each with the builder (`--print --slot ...`) and compare (`tools/compare_spec.py`), and which values a correct extraction must contain (from `expected.md`).

Optional, if time allows: a hand-written reference spec for `changed-a` (`tests/fixtures/spec-changed-a.json`) that passes `spec.py` validation, so `compare_spec.py` can be used.

## Constraints

Do not touch `builder/` (Codex is working in `spec.py`, `offer_check.py`, `workflow.py`). No Freya, no commit, no `env.sh`, no live model calls (the CTO runs them). Report in `tasks/T-006b-report.md`.
