# T-043: a Turkish final-style case folder, and the fixed tool names in hidden-03

No builder code change, no Freya, no model call, no commit.

## Build command (yours to run)

```bash
python3 builder/build.py organizer-sim/hidden-04-tr https://<our-mock-url>
# offline render first:
python3 builder/build.py --print --slot rehearsal-tr organizer-sim/hidden-04-tr https://<our-mock-url>
```

The folder has no OpenAPI file, only the PDF contract. So the build makes one model call to derive the OpenAPI file (T-040) and writes it to `traces/<slot>.openapi.json`.

## The folder `organizer-sim/hidden-04-tr/`

Lale Bankası (fictional), Turkish, credit-card statement arrears, one or two cards. No value is copied from the kit.

| File | Contents |
|---|---|
| `BRIEF.md` | Summary, document priority, the 7 tools, call inputs (`musteri_no`, `ad`, `soyad`, `hitap`, **`simdi`**) |
| `README.md` | What each document is |
| `politika/arama-politikasi.docx` | The main policy: opening (KVKK recording sentence), identity (last 4 of the national ID number, date of birth as `GG.AA.YYYY`, 2 wrong answers allowed in total), debt, calendar, a 2-row deadline table, amounts and persuasion, read-back, special cases, closing and precedence. Headings, bullets and a table. |
| `politika/takvim-ve-sonuc-kodlari.xlsx` | Sheet `Tatiller`: 4 days stored as **Excel dates**: 2026-10-28 (eve), 10-29, 11-13, 12-30. Sheet `Sonuc_Kodlari`: 16 `sonuc`/`sebep` rows |
| `politika/ek-genelge-2026-10.md` | **A newer circular that overrides the policy:** (1) for 1-30 days late, 80 % of the minimum payment is accepted, rounded up to the kuruş; (2) no Saturday callbacks |
| `sozlesme/servis-sozlesmesi.pdf` | The service contract as a **hand-written, valid PDF** (Flate, correct xref; opened and read with PDFKit). The 7 tools with their own fields: `soru`/`yanit`, `dogrulandi`, `kartlar[].kart_ref/kart_son4/gecikmis_tutar/asgari_odeme/gecikme_gun`, `tutar`/`odeme_tarihi`, `not_kodu`, `arama_tarihi` + `arama_saati`, `birim`, `sonuc`/`sebep`, and the `basarili` result field (not `ok`) |
| `ornekler/test-musterileri.json` | 3 test customers (one with two cards) |
| `ornekler/ornek-konusma-1..3.md` | 3 sample calls in Turkish: a promise; a callback booked with a third party; two cards, one promise and one dispute |

**Regeneration:** the Office and PDF files can be rebuilt with `organizer-sim/tools/make_hidden_04_tr.py` (standard library). `organizer-sim/README.md` has a "Package 4" section.

## What it tests

1. **The final's input form:** a folder, a URL, and a contract given only as a PDF, so the contract derivation runs.
2. **Turkish content:**
   - Turkish rules, a fixed opening sentence in Turkish;
   - Turkish dates ("3 Mart 1985", "haftaya Salı"), Turkish amount formats ("3.850,40 TL");
   - the `{ad} {hitap}` address order ("Ayşe Hanım").
3. **Different fields and values behind the 7 fixed tool names:**
   - the success field `basarili`;
   - identity done when `dogrulandi`;
   - the callback date and time in two fields;
   - a closing with `sonuc` + `sebep`.
4. **Holidays only in Excel,** stored as date cells.
5. **A newer document overrides an older one:**
   - a percentage floor that applies to one band only;
   - the Saturday callback is cancelled;
   - checks the "a later document wins" rule.
6. **Deadlines** of 8 and 4 business days. Persuasion attempt 1 is "this Friday or the last business day before it".
7. **Precedence and the outcome table:** in the xlsx, not in Markdown.

## What I saw with the builder's reader (read-only check, T-040 code)

All 10 files are read with no warnings. The xlsx dates come out as `2026-10-28` and so on, and the PDF text is extracted and attached. Two gaps showed up; both are builder findings to fix if you want, since I did not touch the builder:

1. **The Turkish sample calls are not marked as reference material.** `ornek-konusma-*.md` keeps role `policy`, because the reference words are English and the speaker labels (`Asistan:`, `Müşteri:`, `Arayan:`) are Turkish. The model could take rules from the examples. Fix: add Turkish words (`ornek`, `konusma`, `test`, `musteri(ler)`) and labels (`asistan`, `müşteri`, `arayan`) to `case_folder.role_of`. A small change.
2. **The PDF contract is not marked as the contract** (`sozlesme` is not among the contract words). The derivation then sees every document instead of only the contract. It still works, but with more noise. Fix: add `sozlesme`/`sözleşme` to the contract words.

## hidden-03: the seven fixed names

| Was | Now |
|---|---|
| `confirm_member` | `verify_identity` |
| `fetch_holdings` | `get_account` |
| `log_pledge` | `create_promise` |
| `file_remark` | `add_note` |
| `book_return_call` | `schedule_callback` |
| `route_to_team` | `transfer_to_agent` |
| `end_interaction` | `close_call` |

- Updated in both the brief and the OpenAPI file; fields and values are unchanged.
- `register_bereavement` is removed: the bereavement notice asks nothing else and closes `ESTATE_NOTIFIED` with no tool.
- An update note was added to the T-033 report.
