# T-044 report: close the T-041 gaps (Turkish product names, recording notice, callback times, currency)

**Owner:** claude-dev2.
**Not done:** no Freya request, no commit, no env.sh. The model call is not run here.
**Generic:** Turkish language words only; no brief value. The leak test is green.
**`python3 -m unittest`:** 687 tests, OK. The English Brief A pin (`04f40fd7…`) is unchanged, and a test checks that an English render has none of the new code.

## Fixed on the way: Turkish dates were missing in the several-product check

T-041 put the Turkish date block only into the one-product check. The several-product check (`check_offer` for A+B-style specs) and the special-note code built their prelude by hand, without the language. They now use the same `_prelude`.

## 1. Product names in the call's language

**Translation input:** `language.product_word_entries(spec)` adds these entries to the ONE translation call:
- `WORD_NAME_WITH_LABEL` = "{kind} ending {label}", so the word order can change ("{label} ile biten {kind}");
- `WORD_PRODUCT`;
- `WORD_NTH` (the ordinal names, one per line);
- `WORD_AND`;
- `WORD_KIND_<value>` for each kind value the spec's offer rules name for the kind field ("credit_card" → "credit card").

Each entry has the same placeholder and line checks as before.

**In the generated code, for a call not in English (`LOCAL_PRODUCT_NAMES`):**
- `product_name` builds the name from the translated words. An unknown kind falls back to its own words.
- `readback` uses the item pattern with any word order and joins items with the translated "and".
- The English code puts "the " before a name. A translated name is a string whose `startswith('the ')` is true, so no English "the " is added and the English code is unchanged.
- In the translated offer messages, `[product]` and `[next]` are put back as `the [product]` and `the [next]`, the form the code replaces, whatever the word order.

## 2. Recording notice in Turkish

**Introduction rewrite:** `present_recording_notice(text, "tr")` rewrites past, perfect, aorist and future forms on the call to the present: "görüşmemiz kayıt altına alınıyor".
- Covered forms: "kaydedilmiştir", "kaydedildi", "kaydedilir", "kaydedilecek", "kayıt altına alınmıştır", …
- Left as they are: present forms ("kaydediliyor", "kaydedilmektedir").
- "kaydedilebilir" (may be) is left as it is, with a warning.

**System prompt:** for `tr`, the honesty sentence becomes: Use the Turkish word for "recorded" ("kaydedildi") only for an action whose tool returned ok true …; for the recording notice say "görüşmemiz kayıt altına alınıyor".

## 3. Callback times in Turkish

`callback.py`: for `tr`, the day and time words are put in the English words the reader knows before it runs (Turkish date block plus `TURKISH_CLOCK`):

| The customer says | Read as |
|---|---|
| "yarın saat on birde" | 11:00 |
| "öğleden sonra üçte" | 15:00 |
| "14:30" | 14:30 |
| "sabah dokuz buçukta" | 09:30 |
| "öğlen" | 12:00 |
| "iki saat sonra" | in 2 hours |
| "yarım saat sonra" | in 30 minutes |

Text with no Turkish word is left to the English reader as it is.

## 4. Currency

- **Spec:** `agent.currency` is a new optional field. The extraction asks for the currency word the documents write after amounts (for example TL), and leaves it empty when they write none.
- **Generated code:** when the field is set, spoken amounts get it ("637,50 TL"). An empty field adds no code.

## Tests (`tests/test_t044_turkish_names.py`, 9 tests)

- the spec's kinds go into the one call, and the translated words come back;
- Turkish names: "1903 ile biten kredi kartı", "2. ürün", and an unknown kind;
- message slots keep `the [product]`;
- the Turkish notice cases and "may be";
- the Turkish system prompt;
- the Turkish callback times table;
- the currency;
- English has none of the new code;
- a Turkish A+B spec plays every self-check scenario, and its several-product check holds the Turkish reader.

## Open

- **Translation call not run live:** the product word and line translation still needs a real build to check its quality.
- **Kinds the spec never names:** a bank kind value that is not in the spec's rules is said in its own English words.
- **Callback window text:** `_window_text` (for example "on weekdays between …") is still English inside the translated `CALLBACK_OUTSIDE_SAY`.
- **"Çeyrek geçe/kala":** quarter-past and quarter-to times in Turkish are not read.
