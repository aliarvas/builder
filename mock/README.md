# Bank mock (Cloudflare Worker)

The final does not host the bank: this worker is the bank. It must be live before the builder runs and stay up until the results are out.

## What it serves
- `POST /v1/<tool>` or `POST /<tool>` for `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. Behaviour follows the kit mock: three wrong answers in total end the check, `day_month_swapped` hint (not counted), unreadable answers are `ok:false` and not counted, `get_account` and `create_promise` refuse with `identity not verified`, one promise per product, nothing is accepted after `close_call` (`the call is already closed`), fault injection `faults:[{tool,fail_first_n}]` answers HTTP 500 and records nothing.
- `GET /ledger/<customer_id>` (also `/v1/practice/ledger/<id>`): the ledger in the kit's shape (verified, wrong, promises, notes, callbacks, transfers, outcome, reason, failures, calls).
- `POST /v1/practice/sessions {case: "PUB-01" | {case object}}` creates a fresh customer, returns `{variables}` (like the kit).
- `POST /admin/customers {customer_id, variables, identity, products, faults}` adds or replaces a customer (the hidden ones); `POST /admin/reset/<id>` clears a ledger. `GET /health`.
- If the secret `TEAM_KEY` is set, `/practice/sessions` and `/admin/*` need the header `x-team-key`. The tools themselves are open (the agent sends no key).

State: one SQLite-backed Durable Object per `customer_id` (free plan). Customers come from `customers.json` on first use, or from `/admin/customers`.

## Deploy
```
cd mock
npx wrangler login            # the CTO or the user, once
npx wrangler deploy           # prints https://bank-mock.<account>.workers.dev
# optional: npx wrangler secret put TEAM_KEY
curl https://bank-mock.<account>.workers.dev/health
```
The tool URL base is `<that url>/v1` (the kit's openapi has `servers: .../v1`; paths without `/v1` work too).

## Test without wrangler
```
node mock/test/local-test.mjs          # core logic with an in-memory store, 9 groups
cd mock && npx wrangler dev --port 8799   # the real worker and Durable Object locally, then curl
```
`npx wrangler deploy --dry-run --outdir /tmp/x` bundles it (checked).

## Fit to the final contract (minutes, not hours)
| What changes | Where |
|---|---|
| Tool names, argument names, enums (outcomes, reasons, queues), "verified required" per tool | `config.json` -> `tools` |
| Identity questions and their kind (date, N digits), wrong-answer limit, hint text | `config.json` -> `identity`, `wrong_limit` |
| Product id field, response field names | `config.json` -> `product_fields`, `response_fields` |
| Error texts the agent or scorer may match (`identity not verified`, `the call is already closed`, 500 text) | `config.json` -> `errors` |
| Test customers: ids, identity answers, products, faults | `customers.json` (regenerate: `python3 mock/tools/make_customers.py`, or write by hand) |
| A new tool | add an entry in `config.json` and a `case` in `core.js` `handle()` |
| Rules the kit mock did not show and we guessed: a duplicate promise is rejected, `reason` required except `promise`/`paid`, notes need no verification, amounts are not capped by `past_due` | `config.json` flags / `core.js` |
| Scorers' own customers | `POST /admin/customers` before the run, or add to `customers.json` and redeploy |

## Open questions for the final README
1. How do the scorers' customers reach the mock (a customer table in the zip, a seeding call, or created from case data)?
2. Exact ledger shape the scorer reads, and whether it needs `x-team-key`.
3. Whether the mock must enforce brief rules (date windows, amount floors) or only record.
4. Fault injection: how hidden faults are declared (`fail_first_n` per tool in the case).
