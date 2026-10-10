# Collections Domain and Policy

**Owner:** Collections behavior, guardrails and scenario semantics  
**Read when:** Writing extractor rules, prompts, guards or domain tests

## Principle

Policy comes only from the supplied brief and official materials. Never invent jurisdiction rules, holidays, options or amounts. Each consequential rule needs provenance ([`IR-SPEC.md`](IR-SPEC.md)). Hidden briefs must not influence code or prompts.

## Typical call shape `[VERIFIED from the official page and sample]`

1. Confirm who is on the line, then verify identity (security answers via `verify_identity`) before any debt talk.
2. Look up the account (`get_account`) and state what is owed.
3. Ask when the customer can pay; read back amount and date; record with `create_promise` only after the customer agrees.
4. Close, recording the outcome with `close_call`.

Other tools: `add_note`, `schedule_callback`, `transfer_to_agent`. Use them only as the brief authorizes.

Examples of domain rules named on the page: no debt discussed before identity checks, no promises on holidays, nothing said to relatives. The exact rules come from each brief.

## Rule families to expect in any brief `[VERIFIED from practice briefs; values vary per brief]`

The builder must handle these as data, never as hardcoded values:

- **Opening/disclosure:** what may be said before identity is confirmed, who counts as confirmed, recording notice, handling "are you a robot".
- **Third party / wrong number / deceased:** what to say, callback windows and slots, which outcome and reason to close with.
- **Identity:** which questions, in which order, formats to send to the tool, wrong-answer limits, swapped-format hints, refusal handling.
- **Calendar:** business days, holiday lists, deadline per band (by days late), how "next/this weekday" and vague periods are interpreted.
- **Amounts:** full amount first, floors per product type, what to do below the floor, never asking "how much can you pay".
- **Persuasion:** number of attempts per band, what each attempt proposes, when to stop, what counts as a flat refusal.
- **Special situations:** hardship, dispute, already paid, restructuring request, human request, scam question, unanswerable question.
- **Recording:** read-back and explicit confirmation before recording, one promise per product, retry once on failure then a service-error outcome, required closing sentence after a recorded promise.
- **Multiple products:** order, per-product bands and deadlines, one combined read-back, notes for products without promise, closing precedence.
- **Closing:** exactly one `close_call`, last tool call, goodbye first, outcome/reason table.

Which of these apply, and their values, come only from the brief at hand. The practice briefs (A, B) illustrate the families; a different brief may drop, add or change any of them.

## Safety invariants

- No account or debt details before the required identity verification.
- Do not invent balances, due dates, options or consequences; state only what tools returned.
- Offer only what the brief authorizes. No threats or unsupported legal claims.
- Do not claim a promise, note, callback or transfer was recorded unless the tool result confirmed it.
- Record the promise on the correct product, with a valid date and amount, exactly once.
- Understand natural speech: numbers split in two parts, self-corrections, amounts and dates in words. Read back and confirm before recording.
- Handle the call date through `now`, never a fixed date.
- Missing or conflicting critical rule: use a documented safe limited behavior or fail the build.

## Scenarios to support `[HYPOTHESIS until practice cases are read]`

| Scenario | Minimum safe behavior, subject to the brief |
|---|---|
| Wrong person / third party | No private disclosure; end or ask for the intended person; record the right outcome. |
| Identity failure or refusal | Limited disclosure; follow the brief's exit path; record `not_verified`-style outcome. |
| Dispute or already paid | No promise; record a dispute or note as the brief says. |
| Promise date not allowed (holiday, window) | Do not record; offer an allowed date. |
| Multiple products (Brief B style) | Ask or choose per the brief; record on the right product. |
| Refusal to pay | Close politely; record no-promise outcome. |
| Callback or human request | Use `schedule_callback` / `transfer_to_agent` as authorized. |
| Corrections mid-call | Use the last confirmed value; re-read back. |

## Enforcement levels

- **Platform guard:** enforced by a Freya feature (node-scoped tools, transitions on tool results).
- **Code guard:** enforced by generated code such as a pre-call check.
- **Prompt:** told to the model, not guaranteed.
- **Test-only:** detected afterwards.

Record each critical rule's real enforcement level. Never label a prompt instruction as a guard.
