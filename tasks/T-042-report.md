# T-042 report: bank mock as a Cloudflare Worker

**Owner:** claude-reviewer. No Freya, no commit, no env.sh, no Cloudflare login. Everything is in `mock/`.

## Done
| File | Purpose |
|---|---|
| `mock/worker.js` | Worker entry (routes by `customer_id`) and the `Ledger` Durable Object (SQLite-backed, free plan). Imports `config.json`, `customers.json`, `cases.json`. |
| `mock/core.js` | All logic, no Cloudflare API (so node can run it). `handle({method, path, body, headers, state, config, cases, env, newId})`. |
| `mock/config.json` | Tool and argument names, enums, wrong-answer limit, identity fields, error texts, response field names. |
| `mock/customers.json`, `mock/cases.json` | The 13 public customers (ids `c_pub-01`…`c_pub-13`) made from the kit's test set by `mock/tools/make_customers.py`. |
| `mock/wrangler.toml` | Durable Object binding `LEDGER`, migration `new_sqlite_classes = ["Ledger"]`. |
| `mock/README.md` | Deploy steps, endpoints, contract fit table, open questions. |
| `mock/test/local-test.mjs` | Node test, in-memory store. |

## Behaviour (reference: kit openapi and the ledgers in `traces/live-runs`)
- Seven tools at `/v1/<tool>` and `/<tool>`. Ledger shape as the kit's (`verified`, `wrong`, `hinted`, `promises[{promise_id,product_id,type,amount,date}]`, `notes`, `callbacks`, `transfers`, `outcome`, `reason`, `failures`, `calls[{n,tool,args,status,result}]`, `last_at`).
- `verify_identity`: `wrong_answers_left` starts 3 and falls on each wrong answer; the third wrong ends the check (later calls `too many wrong answers`); `day_month_swapped` hint is not counted; unreadable date/digits are `ok:false` and not counted.
- `get_account`, `create_promise` before both answers: `identity not verified` (the text `tools/score.py` looks for). One promise per product; unknown product, bad amount or date are `ok:false`.
- After `close_call` every call answers `the call is already closed`. `close_call` needs `reason` except for `promise` and `paid` (ledger reason `null` then).
- Faults: `faults:[{tool, fail_first_n}]` give HTTP 500 `service unavailable, nothing was recorded`, nothing recorded, counted in `failures` (the PUB-10 shape).
- Our own endpoints: `GET /ledger/<id>` (and `/v1/practice/ledger/<id>`), `POST /v1/practice/sessions {case}` (same reply shape as the kit), `POST /admin/customers` (add the scorers' customers), `POST /admin/reset/<id>`, `GET /health`. `TEAM_KEY` secret optional for the practice/admin endpoints.

## Tested
- `node mock/test/local-test.mjs`: 9 groups pass (happy path with exact response shapes, nothing after close, lock after three wrong, hint and unreadable input, PUB-10 fault, notes/callback/transfer/validation, third party callback, practice session/reset/unknown customer, admin upsert and key check).
- `npx wrangler deploy --dry-run` bundles (37 KiB); the DO and TEAM bindings are shown.
- `npx wrangler dev` on port 8799 (local, no login): `/health`, `verify_identity` -> verified, `get_account` -> `identity not verified`, `GET /ledger` shows the stored call. The Durable Object state works.

## Fitting to the contract after 20:00 (minutes)
| Change | File |
|---|---|
| Tool/argument/field names, enums, `requires_verified`, error texts | `config.json` |
| Identity questions and kinds, wrong-answer limit | `config.json` `identity`, `wrong_limit` |
| Test customers (ids, answers, products, faults) | `customers.json` (script or by hand) |
| Hidden customers at run time | `POST /admin/customers`, or add to `customers.json` and redeploy |
| A new tool | one `config.json` entry plus one `case` in `core.js` |
| Guessed rules (listed in the README): duplicate promise rejected, reason rule, notes need no verification, amount not capped | `config.json` / `core.js` |

## Open questions for the final README
1. How the scorers' customers reach the mock (table in the zip, seeding call, or cases)?
2. What ledger shape and auth the scorer reads.
3. Whether the mock enforces brief rules (date windows, floors) or only records. I record only.
4. How hidden faults are declared.

## T-038 left unfinished (you stopped it)
My edits are in the shared tree, uncommitted and not finished: `builder/offer_check.py` (`REFUSAL_CLEAR` after a refusal, `pick_products` fallback for the only or the one accepted product) and `builder/workflow.py` (the date route skips refusal values, `offer_date` description, `confirm_record` extracts the offer fields and goes to `check_offer` when a revise carries a date or amount). No self-check scenario and no new tests written. Suite now: 659 tests, 2 failures, neither from these edits as far as I can tell: the prompt-document test (`docs/PROMPTS.md` stale, another agent's change) and the string-literal leak test (`'type'`, `'English'` embedded literals, from another agent's change). Earlier in the session three tests failed after my edits (`test_multi_step`, `test_notes_outcome` byte-identical render, `test_offer_date_only` transition check); they pass in the last run, I did not check why (someone may have updated them). Please confirm before committing. Tell me if I should revert or finish T-038 later.
