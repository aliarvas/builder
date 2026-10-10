# T-009b review (bütçe aşımında durma yok, kapanış etiketleri, gerçek veri kontrolü)

Rapor: tasks/T-009b-report.md. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 225 test geçiyor. Kendi çalıştırmalarımı repo dışındaki bir scratch dizininde yaptım (repo trace dosyalarına dokunmadım). claude-dev2'nin docs/ güncellemeleri dahil değil.

## Karar: merge edilebilir
Üç istek de doğru uygulanmış. Kalan notlar bilgi düzeyinde.

## 1. Bütçe aşımı build'i durdurmuyor: doğrulandı
- Etiketsiz canlı A+B spec'i (`tests/fixtures/extract/brief-ab-extracted.json`, `--spec … --print`, `build.main`): **çıkış kodu 0**, stdout saf JSON (ayrıştırılabilir), stderr'in son satırı:
  `warning: prompt budget exceeded but shipped: negotiate: ~1596 tokens > limit 1500 after all budget stages; shipped with every rule (see traces/<slot>.print.log)`.
- Trace: `budget: negotiate: ~1680 -> ~1596 tokens (target 1200, limit 1500)`, `budget: stages: duplicate wording removed`, `budget_exceeded_but_shipped: negotiate: ~1596 tokens > limit 1500 after all budget stages; shipped with every rule`, `status: ok`; 84 `rule_placement` satırı, hiçbir kural prompt dışına çıkmamış (etiket yok, koda giden yok).
- `--print` uyarıyı stderr'e (stdout workflow JSON'u), kaydetme/`--validate` modu stdout'a yazıyor (`summary_stream`, `build.py` ~341–345; coverage uyarısı varsa en sonda o). Spec uyarısı da "over the hard limit 1500; shipped anyway, no rule cut". SpecError artık yalnızca bütçe için fırlatılmıyor.
- Hedef–sınır arası (1200–1500) davranışı değişmedi: yalnızca uyarı. Aşamalar aynı; 60 sentetik kural testi aşım satırını ve son kuralın prompt'ta kaldığını doğruluyor.
- Bilgi: ~1600 token'lık bir `negotiate` gönderiliyor; rapor haklı olarak güvenilirlik riskini not ediyor. Canlı koşuda `budget_exceeded_but_shipped` görünürse ilk bakılacak şey modelin `enforced_by` etiketlerini koyup koymadığı.

## 2. `closing_outcome` etiketli kurallar varsayılan olarak prompt'ta: doğrulandı
- `RulePlan` kapanış kurallarını baştan koda almıyor; hepsi global prompt'tan başlıyor (not: "closing rule, no step prompt").
- Bütçe yeterliyse: küçük bir spec'te etiketli bir kapanış kuralı yerleşim satırında `global prompt (… code also enforces closing_outcome, kept: within budget)`, yani kural prompt'ta kalıyor (kendim denedim).
- Baskı altında: etiketli A+B kopyasında 8 kapanış kuralından 4'ü (etiketliler) koda, 4'ü (etiketsiz) global prompt'ta; `negotiate` ~1680 → ~1314, aşım satırı yok. Etiketsiz kapanış kuralları her durumda global prompt'ta. Böylece yanlış etiketlenmiş bir kapanış kuralı artık yalnızca bütçe baskısında kaybolur; bütçe sorunsuzken kaybolmaz (önceki review bulgu 1 kapandı).

## 3. `enforcement_available` gerçek veriye bağlı: doğrulandı
Fixture A ile hepsi `True`; offer verisi boşaltılmış bir kopyada (`latest`, `min_amount`, `max_amount` boş, iş günü kapalı, `next_weekday = ask`) şöyle:

| Etiket | Veri yokken |
|---|---|
| `offer_dates` | **False** (`latest` boşsa son tarih kuralını koda saymıyor) |
| `business_days` | False |
| `offer_amounts` | False |
| `weekday_reading` | False |
| `invalid_offer_limit` | True (`max_rejected_offers` zorunlu ve ≥ 2) |
| `identity_attempts` | True (deneme sayacı alanı ve en az bir kimlik sorusu var) |
| `closing_outcome` | True (kapanış tablosu ve `outcome_field` var) |

Son üçü pratikte her geçerli spec'te `True`, çünkü spec onları zaten zorunlu kılıyor; yine de gerçek alanlara bakıyor ve boş değerde `False` verir. Verisi olmayan etiketli kural prompt'ta kalıyor ve trace "tagged X but this spec has no data for that check, kept" yazıyor (testli).

## Bilgi notları
- Herhangi bir adım hedefi aşınca `GLOBAL` da aşama kapsamına giriyor, yani tek bir adımın (ör. identity ~1235) fazlalığı etiketli global/kapanış kurallarını tüm adımlardan çıkarır. Her adım global prompt'u içerdiği için kasıtlı ve savunulabilir.
- `f041-a` canlı spec'inde `negotiate` ~1408 → ~1332: hedefin üstünde, sınırın altında; yalnızca uyarı (aşım satırı yok), beklenen.

## Kurallara uyum
Freya/model isteği yok, stdlib; prompt metinleri değişmemiş (`docs/PROMPTS.md` aynı); `run_trace.py` ve `submission_check.py` dokunulmamış.
