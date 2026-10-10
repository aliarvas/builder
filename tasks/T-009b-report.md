# T-009b raporu: bütçe build'i durdurmaz; kapanış etiketleri ve gerçek veri kontrolü

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10 · **Kaynak:** CTO kararı ve `reviews/T-009-review.md` bulgu 1–3

## Özet

- **Testler:** `python3 -m unittest` 225 testin hepsini geçiyor; `tests/test_prompt_budget.py` 12 test (öncesi 10).
- **Değişen dosyalar:** `builder/workflow.py`, `builder/build.py` (render trace satırları ve son satır uyarısı), `tests/test_prompt_budget.py`, `docs/ARCHITECTURE.md` (bir cümle).
- **Prompt'lar:** Prompt metni değişmedi; `docs/PROMPTS.md` yeniden üretildi ve aynı kaldı.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.

## 1. Bütçe aşımı build'i durdurmuyor (CTO kararı)

- **Hedef ve sınır:** Hedef 1200, sınır 1500; aşamalar aynı. Ama tüm aşamalardan sonra 1500'ü aşan adım için artık `SpecError` yok: adım **bütün kurallarıyla gönderiliyor**.
- **İz:**
  - **Placement satırı:** `budget_exceeded_but_shipped <adım>: ~N tokens > limit 1500 after all budget stages; shipped with every rule`.
  - **Trace:** `build.py` bunu `budget_exceeded_but_shipped:` anahtarıyla yazıyor.
  - **Spec uyarısı:** "over the hard limit 1500; shipped anyway, no rule cut".
  - **Son çıktı satırı:** `warning: prompt budget exceeded but shipped: … (see traces/<slot>…)`.
    - Kaydetme ve `--validate` modunda stdout'a gidiyor.
    - `--print` modunda stderr'e gidiyor, çünkü stdout workflow JSON'u. Bu, coverage uyarısıyla aynı kural.
    - Coverage uyarısı da varsa en sonda o geliyor.
- **Etiketsiz canlı A+B spec'i** (`brief-ab-extracted.json`): `negotiate` 1680 → 1596 token, build exit 0 ile tamamlanıyor, yukarıdaki satırlar yazılıyor. Hiçbir kural prompt dışına çıkmıyor; etiket olmadığı için koda giden kural da yok.

## 2. `closing_outcome` etiketli kurallar varsayılan olarak global prompt'ta (bulgu 1)

- `RulePlan` artık etiketli kapanış kurallarını baştan koda almıyor. Bütün kapanış kuralları global prompt'tan başlıyor (not: `closing rule, no step prompt`).
- Etiketli olanlar yalnızca bütçe aşımında, diğer etiketlerle aynı aşamada (`drop_code_enforced`) koda alınıyor.
- Bütçe yeterliyse trace nedenini yazıyor: `code also enforces closing_outcome, kept: within budget`.
- **Etkisi:** Yanlış etiketlenmiş bir kapanış kuralı (kodun yapmadığı mantık) bütçe aşımına kadar prompt'ta kalıyor. Etiketli A+B'de `negotiate`'in "önce" değeri 1595'ten 1680'e çıktı; "sonra" değeri yine ~1314, çünkü baskı altında aynı kurallar koda alınıyor.

## 3. `enforcement_available` gerçek veriye bakıyor (bulgu 3)

| Etiket | Artık geçerli olma koşulu |
|---|---|
| `offer_dates` | `offer.latest` boş değil (yalnız `earliest` son tarih kurallarını kapsamaz) |
| `business_days` | değişmedi: `promise_date_must_be_business_day` açık |
| `offer_amounts` | değişmedi: tutar kuralı var |
| `weekday_reading` | değişmedi: `next_weekday` `ask` değil |
| `invalid_offer_limit` | `max_rejected_offers` pozitif bir tam sayı |
| `identity_attempts` | `identity.attempts_left_field` dolu ve en az bir kimlik sorusu var |
| `closing_outcome` | kapanış tablosunda satır var ve `closing.outcome_field` dolu |

Koşul tutmazsa kural prompt'ta kalıyor ve trace "tagged X but this spec has no data for that check, kept" diyor.

## Testler

- **Değişen:**
  - Etiketli A+B: bütçe satırı `~1680 -> ~13xx`, aşım satırı yok.
  - Etiketsiz A+B: build durmuyor; aşım satırı, uyarı ve tam kural yerleşimi var; koda giden kural yok.
  - 60 sentetik kural: aşım satırı var, son kural prompt'ta duruyor.
  - Etiketli kapanış kuralı: bütçe içinde global prompt'ta, baskı altında kodda; etiketsiz kural her durumda global prompt'ta.
- **Yeni:**
  - `offer_dates` etiketi `latest` boşken kuralı prompt'ta tutuyor; fixture A'da yedi kontrolün hepsi mevcut, bilinmeyen değer değil.
  - CLI (`build.main`, `--spec brief-ab-extracted.json --print`): exit 0; stdout saf JSON; trace'te `budget_exceeded_but_shipped: negotiate: ~1596 tokens > limit 1500`; stderr'in son satırı uyarı.

## Not

Bütçe aşımında build durmadığı için etiketsiz çok ürünlü bir çıkarma artık ~1600 tokenlık bir `negotiate` ile gönderilir. Bu, sıfır puandan iyi; ama uzun prompt sabit modelin güvenilirliğini düşürebilir. Canlı koşularda trace'teki `budget_exceeded_but_shipped` satırına bakın. Görünüyorsa modelin `enforced_by` etiketlerini koyup koymadığı ilk kontrol edilecek şey.
