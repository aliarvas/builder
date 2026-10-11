# T-033: a third unseen brief, built to push the builder off familiar ground

I made no builder code change, no Freya action, no model call and no commit. `python3 -m unittest` still gives 644 OK; the new files are not read by any test.

## Files

| Path | What |
|---|---|
| `organizer-sim/hidden-03-twists/brief.md` | Brief D: "Halvard Building Society", member arrears on two holdings |
| `organizer-sim/hidden-03-twists/openapi.json` | 8 POST tools; the server is `https://halvard-society-organizer-sim.invalid/api` (`.invalid` kept) |
| `organizer-sim/README.md` | a "Package 3" section with the build command |

**Build command (yours to run):**
```bash
python3 builder/build.py organizer-sim/hidden-03-twists/brief.md organizer-sim/hidden-03-twists/openapi.json
```

**The format follows hidden-01:**
- one Markdown brief and one OpenAPI 3.0.3 file;
- each tool's path is its name (`/confirm_member`, and so on);
- `operationId` is set to the same name.

**Checked offline:**
- `builder/tools_from_openapi.py` reads all 8 tools with the right names.
- Its only warning is the usual "format moved into the description" (`log_pledge.pledge_on`).

**Values:** none copied from the kit's public briefs, hidden-01 or hidden-02.
- The holidays differ from every one of those lists: 2026-11-20, 2026-12-08, 2026-12-26 and 2027-01-02.
- The callback window, the tool and field names, the result codes, the identity questions and the bank name are all new.

## What each twist tests

| # | Twist in Brief D | Rule | What the builder must do | Risk |
|---|---|---|---|---|
| 1 | Call inputs renamed: `member_ref`, `salutation`, `surname`, and the time is in **`call_time`**, not `now` | §1 | Find the today variable and the address form from the brief | today_variable must become `call_time` |
| 2 | **Three identity questions**: mother's maiden name, postcode, year of birth, each with its own format (capitals, no space, 4 digits; "'84" means 1984) | 11–12 | Three questions in order, through `confirm_member` with `question`/`answer` (not `check_type`/`response`) | Medium |
| 3 | **Wrong answers counted per question**: one retry per question, and wrong answers to different questions do not add up | 14 | The identity end comes from the tool's `checks_ended` / `all_passed`, not from a total count | **High**: Brief A and hidden-01 both count wrong answers in total |
| 4 | A spelling retry (`needs_spelling: true`) does not count | 13 | The format-retry flag has a new name | Medium |
| 5 | Overall pass field named `all_passed` | 17 | The T-026/T-032 identity hook must use it | Low |
| 6 | **Working days Monday to Saturday**: only Sunday is closed, and two holidays fall on a Saturday | §6 | `non_business_weekdays = [7]` | Medium |
| 7 | **Mixed units for the deadline**: standard tier is 14 *calendar* days, moved to the **previous** working day; escalated tier is the 5th *working* day | §6 | `latest` rules with `unit` calendar or business, and `latest_on_non_business_day = previous` | Medium |
| 8 | **A named Sunday or closed day is moved backwards**: the working day *before* it (or after, if that is before today) | 23 | **Not supported today**: `offer_check.py` always uses `shift_to_business(day, 1)` (forward) | **High**: an expected gap; the spec must not silently claim "next" |
| 9 | Two products with new names: `holdings`, `holding_ref`, `holding_type` (`store_card` / `improvement_loan`), `last_digits`, `arrears_total`, `arrears_days`; floors in `min_repay` / `monthly_repayment` | 18, 28 | Account mapping (kind field, label field, products field) and the floor per kind | Medium; it also exercises T-031's matcher on new kind words ("the store card", "the loan", "both") |
| 10 | **Persuasion differs from Brief A**: attempt 1 offers the *floor* on the latest date; attempt 2 (standard tier only) offers the floor on the 2nd working day, or the latest date if earlier | 31–32 | Persuasion rules from the brief, not Brief A's "last business day of this week" pattern | **High**: any Brief A habit shows here |
| 11 | **Callback window**: never the same day; only the next day or the day after; Monday to Saturday; 09:15–16:45; one combined field `slot_start` (`YYYY-MM-DDTHH:MM`) | 5–6 | A window with no "today" and calendar days, not business days; date and time sent in one field | **High**: today's callback shape is date + time |
| 12 | **New special path: bereavement notice.** It can come **before identity** and from a third party; it has its own tool (`register_bereavement` with a `relationship` enum); it closes `ESTATE_NOTIFIED` whether or not the tool succeeded, and the agent may say "registered" only after `ok: true` | 8–10 | A closing special path that starts at every step (opening, third party, identity), asks one question and calls a tool whose failure does not change the close | **High**: hidden-01 has "deceased" as a plain close with no tool |
| 13 | **New special path: formal insolvency.** It stops payment talk for **every** holding, files `insolvency` for each unfinished holding and ends `INSOLVENCY_STOP` | 40 | One special path that notes all remaining products, not only the current one | **High** |
| 14 | Hardship declined → a `hardship` remark and **continue** (it does not close) | 41 | A per-product note path that returns | Medium |
| 15 | **One result field**: `end_interaction.result_code`, 17 uppercase codes, with no reason field | §10 | An outcome table with an empty reason column; `close_call` is now `end_interaction` | Medium |
| 16 | **Precedence**: bereavement > insolvency > transfer > pledge > system failure; a pledge logged before a transfer still ends `REFERRED_*` | 51 | Outcome order taken from the brief | Medium |
| 17 | Three transfer teams with new names: `member_support`, `repayments`, `branch_adviser` | 41–43 | Queue names from the enum | Low |
| 18 | Different tool names everywhere: `log_pledge` (`pledge_value`, `pledge_on`), `file_remark` (`remark`, `comment`), `book_return_call`, `route_to_team` (`team`) | — | No tool or field name assumed from the kit | Medium |
| 19 | Different spoken lines: the opening sentence, the scam answer (the number on the card or passbook), "payments can take up to three working days", and the text-message line after a pledge | 1, 37, 38, 45 | Fixed lines taken from the brief | Low |

## What to look at after the build (suggested)

1. **Spec:**
   - `offer.today_variable = call_time`;
   - `non_business_weekdays = [7]`;
   - the two `latest` rules (calendar with `previous`; business);
   - `persuasion_attempts` of 2 and 1;
   - the floors from `min_repay` / `monthly_repayment`.
2. **Rule 23 (backwards move):** see whether the spec or the self-check warns, or whether the builder silently moves forward. I expect a gap here; that is the point of the twist.
3. **Identity:**
   - three questions in order;
   - the end of the checks comes from the tool fields (`checks_ended`, `all_passed`), not from a total of two wrong answers.
4. **Callback:**
   - same-day calls refused;
   - Saturday allowed;
   - `slot_start` filled as one date-time.
5. **Special paths:**
   - bereavement can start at the opening and at the third-party step, and closes `ESTATE_NOTIFIED`;
   - insolvency writes a remark for every unfinished holding.
6. **Outcomes:** 17 codes, an empty reason column, and the precedence of rule 51.
7. **Self-check report:** the `unreached_rows` warnings and the spec failures.

## Note: a variant not included

Real APIs often have a path that differs from the `operationId` (for example `/members/confirm` with `operationId: confirm_member`). The builder names tools from the path (`_unique_tool_name`), so the brief's tool names would then not match. I kept the paths equal to the tool names, as in the kit and hidden-01, so this brief tests the policy twists. If you want that risk tested too, it is a separate small package.
