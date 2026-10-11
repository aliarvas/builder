# T-042 (FINAL, urgent): a generic bank mock as a Cloudflare Worker

**Owner:** claude-reviewer. Stop T-038; this comes first.

## Facts

- In the final the organizers do not host the bank. We write and deploy our own mock from the service contract and the test customers, on Cloudflare Workers.
- The mock must be live before the builder runs, and must stay up until the results are out.
- The agent may call only our mock. If the mock is wrong or down, those calls fail.
- The scorers use their own hidden customers against OUR mock. So the mock must answer correctly for any customer data they send, or for a customer table we ship. Read the final README when it comes.

## Prepare now, before the contract is known

1. **The worker.** In `mock/`, write `worker.js`: one Cloudflare Worker (ES module) that serves POST `/<tool>` for the seven tools.
   - `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent` and `close_call`. Use the kit's mock behaviour as the reference: `build-the-builder-v2/tools/openapi.json` and the fields seen in `traces/live-runs/*.json` ledgers.
   - **Customer data:** a `customers.json` bundled at deploy time (imported as a module).
   - **State:** a ledger per `customer_id`. Use a Durable Object, or KV if simpler. In-memory state is not reliable across isolates. Use a Durable Object if wrangler supports it without a paid plan; otherwise KV.
   - **Rules from config:** wrong-answer limit, field names and allowed values come from one `config.json`, so the final contract can be mapped quickly.
   - Add a GET `/ledger/<customer_id>` for our own checks, and a reset.
2. **`wrangler.toml`** and a `mock/README.md` with the deploy steps (`npx wrangler deploy`). The CTO and the user will log in; you do not run wrangler login.
3. **Local test.** Run the worker logic with node, without wrangler: a small node script that imports the handler with an in-memory store and plays a happy path, wrong answers, a promise, a note and a close.
4. **Fit to the contract after 20:00.** Write down which parts change when the contract arrives (field names, the identity questions, products), so the change takes minutes.

## Constraints

- No Freya, no commit, no env.sh, no Cloudflare login.
- Report: `tasks/T-042-report.md`.
