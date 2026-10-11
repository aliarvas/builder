# T-011 — Closing outcome derived from product notes (AB-FRESH risk 5)

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

In a multi-product brief the call outcome can depend on the per-product notes. Example of the general pattern: no promise, every product noted with one reason → that reason's row; otherwise the reason of the first other note. Today such rows are named only by a returning special path, the closing never derives them, and the call closes with the default row. The self-check reports these rows as BUILDER warnings (`tasks/AB-FRESH-report.md` risk 5, `tasks/T-010-report.md`).

## What to build

1. **An optional spec block.** Follow the proposal in `tasks/AB-FRESH-report.md` (risk 5), for example `closing.product_notes.outcome_from_notes`. Add it to the extraction schema, prompt, check and evidence the same way as the other optional blocks. The block is dropped with a warning if it is invalid. Values come only from the documents.
2. **Closing code.** Compute the outcome from the notes in account order, after the note loop. The note loop must therefore run before the outcome is chosen. Coordinate the closing / `note_next` order: claude-dev2 owns that code but is on T-012 in `selfcheck` files only, so you may change it and flag it in the report.
3. **Self-check.**
   - The expected ledger uses the block, so the risk-5 rows become reachable.
   - The `KNOWN` gaps in `tests/test_selfcheck.py` shrink.
   - Coordinate with claude-dev2 (T-012) on `builder/selfcheck.py`. Keep your change there small, at the expected ledger only.
4. **Single-product briefs** (no block) render exactly as today. Prove it with a byte-identical render of `spec-brief-a.json`.

## Tests

- A+B fixtures:
  - all products already paid → the paid row;
  - one dispute plus the others paid → the dispute pair.
- Brief A render unchanged.
- Leak test green.
- `python3 -m unittest`.

## Constraints

No Freya, no live model call, no commit, no `env.sh`, no brief values in `builder/`. Write the report in `tasks/T-011-report.md`, with a short design note at the top.
