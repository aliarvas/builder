# T-048 report: final mock (status: BLOCKED on inputs, 17:32 UTC)

**What is in `~/Desktop/final-case/case/` (unchanged since 17:10 UTC, checked every 5 s for 20 minutes):** only `BRIEF.md` and `statement-debt-call-flow.pdf`. The folders `sources/` (integration document, section 6), `test-environment/` (`test-customers.md`, `test-customers.json`, rules), `cloudflare-mock/`, `README.md` and `example-scenarios.md` have **not arrived**. The sync does not seem to be running (no new file, no change of the folder time). I searched Desktop, Downloads and Documents for the files: not there.

**Why I cannot write the mock yet:** paths, field names, request and response shapes, status codes and the test customers' exact answers all come from those files. Guessing them would produce a mock that fails the scorers' calls. Nothing is written from guesses.

**Prepared (generic, no case content):**
- `mock-final/wrangler.toml`: Worker `freya-final-mock`, Durable Object binding `STATE` (class `CustomerState`, SQLite, free plan), as in T-042.
- The pattern to reuse from `mock/` (T-042): `core.js` with an injected store, `worker.js` routing by customer, node test with an in-memory store.

**What the PDF (call flow drawing) already tells us about the services** (names are my reading of the drawing, to be replaced by the integration document):
1. A card-list service for the customer number (eligible cards, how many, card name, last 4/last 6 digits, card selected).
2. Statement debt per card: TL debt with payment status (none paid / minimum or more paid / below minimum paid), USD/EUR/GBP debt, cut-off date, due date, minimum.
3. Cut-off week: read the card's cut-off week, shared statement (primary or linked card), list the other weeks, confirm and change it.
4. Registered e-mail: read it, send the statement by e-mail.
5. Second factor (back to the IVR) and "transfer to agent".

**What I need (from the CTO):** copy the rest of the pack to `~/Desktop/final-case/case/` by hand (or tell me another path), starting with `test-environment/` and the integration document. With them I expect about 30-40 minutes to write, test and deploy (the core and the worker pattern exist; the work is mapping the shapes and the 8 to N test customers).
