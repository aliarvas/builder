# T-048 (FINAL): our mock of the bank's services for the final case

**Owner:** claude-reviewer (stop T-045)

## Facts (BRIEF.md of the final, in `~/Desktop/final-case/case/`)

- **What to build:** our own mock of the bank's services, on Cloudflare Workers. It must have the same paths, the same field names, and the same request and response shapes as the bank's integration document (section 6).
- **Test customers:** for the bank's test customers it returns exactly the answers listed in the pack, HTTP status included. They are in `test-environment/` (`test-customers.md`, `test-customers.json`, plus the rules of the test environment).
- **Hidden customers:** the scorers' simulated customers reach our mock through the workflow's tools. They are probably among these test customers (or match them); check `test-environment/`.
- `cloudflare-mock/` has the organizer's one-endpoint example.

The files are still arriving in `~/Desktop/final-case/case/`; a sync runs every minute. This mock is NOT the builder, so it may use the case content.

## What to build

1. **The Worker.** Write `mock-final/`: a Worker that implements every service of the integration document, section 6, exactly:
   - paths, methods, field names and status codes;
   - error shapes;
   - date logic from `now` where the documents say so;
   - state changes: the cut-off week change and the statement e-mail. Keep these in a Durable Object (like T-042), so a confirmed change is visible later in the call.
2. **Data.** The test customers come from `test-customers.json`, bundled.
3. **Local test.** A node test plays every listed test-customer answer and compares it exactly, status included.
4. **Deploy.** With `npx wrangler deploy` (login is done on this machine). Name the Worker `freya-final-mock` and give the CTO the URL.
5. **Rules.** Write down every rule the test environment states (fixed dates, error cases), and every doubt where the documents disagree.

## Constraints

- No Freya; no builder code edits; no commit.
- Report: `tasks/T-048-report.md`.
