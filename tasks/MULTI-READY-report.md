# MULTI-READY raporu: çok ürünlü vakalar (PUB-11/12/13) A+B render'ında, offline

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11 · **Tür:** yalnız analiz ve test; kod düzeltmesi yok

## Özet

- **Sonuç:** PUB-11 ve PUB-13'ün beklenen ledger'ına (sözler ve kapanış sonucu) üretilen kod ulaşıyor. **PUB-12'ye ulaşmıyor:** reddedilen iki ürünün `refused` notunu yazabilecek bir adım yok (bulgu 1, YÜKSEK). Kitte ledger notları da sayıyor, yani PUB-12 bugün kod yüzünden kaybediliyor; modelin iyi ya da kötü olması bunu değiştirmez.
- **Test:** Yeni dosya `tests/test_multi_ready.py`, 7 test; biri bilinçli `expectedFailure` (bulgu 1). `python3 -m unittest`: 346 test, OK (expected failures=1).
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok. Kod değişikliği yok; `workflow.py`'ye dokunulmadı (claude-dev2 F-056 fix).
- **Not:** Yeni test dosyası, araya giren commit sırasında bir süre diskte görünmedi, sonra aynı içerikle geri geldi. İçeriği kontrol ettim.

## Yöntem

**Spec'ler (dördü de her vakada):**

| Ad | Kaynak | Ürün türü/etiket alanı |
|---|---|---|
| `tagged` | `tests/fixtures/extract/brief-ab-extracted-tagged.json` | yok (F-044 öncesi) |
| `f040-b` | `traces/f040-b.spec.json` | yok |
| `t006-brief-b` | `traces/t006-brief-b.spec.json` | yok |
| `fixture-b` | `tests/fixtures/spec-brief-b.json` (el yazması, güncel biçim) | var |

**Simülatör (`Session`):** Vakalar `public-test-set.json`'dan okunuyor; ürünler `p1..p3`.
- **Modelin payı:** Her müşteri turu için "ideal extraction" veriliyor (`offer_date`, `offer_product_number`, kabul, niyet). Niyet değerleri spec'ten, render edilmiş geçişten okunuyor; spec'ler farklı adlar kullanıyor (`refused_attempts_exhausted`, `refused_attempts_used_up`, `multi_product_intent: no_arrangement`).
- **Gerçekten çalışan kısım:**
  - `offer_setup`, `check_offer`;
  - render edilmiş geçiş koşulları (`and`/`or`, `equals`, `greater_than`…);
  - `create_promise` ön kancası (ürün numarasından id, tarih ve tutar);
  - `confirmation_progress` ve `closing` kodu.
- **Platform kuralı:** Tipli değişkene geçersiz yazma reddediliyor (`PlatformCall` gibi). Hiçbir vakada ret görülmedi.

## Vaka vaka

| | Beklenen ledger | Kod ulaşıyor mu | Modele kalan karar | Risk |
|---|---|---|---|---|
| **PUB-11** üç ürün, tek tarih | p1 220, p2 640, p3 75, hepsi 16 Ekim; `promise` | **Evet**, dört spec'te | "this Friday" 16 Ekim'e kodda çözülüyor. Model her turda ürün numarasını yazmalı ve `create_promise`'ı üç kez çağırmalı. | ORTA: bulgu 3 ve 5 |
| **PUB-12** bir söz, iki ret | p1 510, 15 Ekim; `refused` notu p2 ve p3; `promise` | Söz ve sonuç: **evet**. Notlar: **hayır** | Ret niyeti ve ikna denemeleri (kredi 2, araç kredisi 1) tamamen prompt'ta. | YÜKSEK: bulgu 1 ve 2 |
| **PUB-13** tek tarih, farklı son tarih | p1 300, 30 Ekim; p2 900, 23 Ekim; `promise` | **Evet**, dört spec'te | Kredi için 30 Ekim'e kod `date_too_late` diyor ve "Friday, 23 October" öneriyor. "Yes" önerilen tarihi alıyor; okuma iki tarihi de söylüyor. | DÜŞÜK |

## Bulgular ve öneriler (kod değişikliği yapılmadı)

### 1. YÜKSEK: Sözü olmayan ürünlerin notunu yazan bir adım yok (Brief B kural 8 ve 11)

- **Kural 8:** "For each product without a promise call `add_note` … `refused`, …".
  - `add_note` yalnızca ürün düzeyindeki özel yollarda var (already paid, dispute).
  - `negotiate`, `offer_say`, `revise_ask`, `confirm_record` ve kapanış adımlarında `add_note` yok.
  - Hiçbir kod adımı not yazmıyor.
  - `offers_noted` yalnızca geçersiz teklif sınırıyla kapanan ve özel yolla not edilen ürünleri tutuyor; çağrıya hiçbir zaman not olarak gitmiyor.
- **Kural 11:** İki kez başarısız olan `create_promise` için `service_error` notu.
  - `confirm_record` prompt'u bu kuralı söylüyor ama adımda `add_note` aracı yok; model kurala uyamaz.
  - `confirmation_progress` `exhausted` olunca doğrudan kapanışa gidiyor.
- **Spec tarafı:** Etiketli spec ve `f040-b`'de kural 8 `coverage.unmapped` listesinde. `t006-brief-b`'de eşlenmiş görünüyor, ama render'da yine araç yok.
- **Etkisi:** PUB-12 kaybediliyor. Kural 11'in tetiklendiği her çok ürünlü vaka da kaybedilir. Ayrıca "no_promise, ilk notun nedeni" kapanış kuralı not okuyamıyor (bu üç vakada yok).
- **Öneri (kod sahipli):**
  1. Ürün başına bir not nedeni durumu tutulsun: `refused`, `service_error`, ya da özel yoldan `paid`/`dispute`/`hardship`.
  2. Kapanıştan önce bir döngü: bir kod adımı söz kaydedilmemiş ve henüz not edilmemiş bir sonraki ürünü seçsin; sessiz, passthrough bir `add_note` `api_request`'i (`product_id` ve nedenle) onu not etsin; ürün kalmayınca kapanışa geçilsin.
  3. Transfer olduysa döngü atlanmalı (kural 10).

  Notu model yazmıyor; ledger'ı kod garanti ediyor. Test `test_pub12_refused_products_are_noted` (`expectedFailure`) bu düzeltmeyle geçmeli.

### 2. YÜKSEK/ORTA: Bir ürünün reddi bütün pazarlığı bitiriyor

- **Mevcut yönlendirme:** `negotiate` → `confirm_record` / `closing`, niyet "denemeler bitti" ve kabul sayısına göre.
  - PUB-12'de kart kabul edildikten sonra kredi reddedilince akış hemen okumaya gidiyor.
  - Araç kredisi hiç konuşulmuyor; ancak müşteri ikisini tek cevapta reddederse sorun olmuyor.
- **Kontrol "one attempt on the car loan":** Bu durumda kaçar.
- **Kod tarafı:** Ret ürünü not edilmiş saymıyor (`offers_noted` boş kalıyor; test `test_refusal_of_one_product_skips_the_products_after_it`). Ürün başına ikna denemelerini sayan kod da yok; bant başına deneme sayısı (geç bantta 2, erken bantta 1) yalnızca prompt'ta.
- **Öneri:** "Denemeler bitti" niyeti bir kod adımına gitsin. Bu adım şunları yapmalı:
  1. o anki ürünü `refused` olarak işaretlemek;
  2. ürün kaldıysa sonraki ürünün cümlesiyle (`more`) devam etmek;
  3. kalmadıysa okumaya (söz varsa) ya da kapanışa gitmek.

  İkna deneme sayacı da ürün başına kodla tutulabilir (`invalid_offer_limit` gibi). Bu, bulgu 1'in not durumunu besler.

### 3. ORTA: "Hepsi aynı gün" tek turda kontrol edilemiyor

- **Kısıt:** Extraction yalnızca tek bir ürün numarası taşıyor. Çok üründe numara boşsa sonuç `product_unknown` ("Which of your products is this payment for?"; test `test_pub11_one_turn_for_all_three_still_needs_two_more_turns`).
- **PUB-11'deki sonuç:** Ledger'a ulaşılıyor ama üç kontrol turu gerekiyor. Her `more` cümlesi müşteriye zaten kabul ettiği ürünü soruyor ("The amount due is 640. Could you pay 640?"). Konuşma uzuyor ve müşteri "zaten söyledim" diyebilir. Model numarayı her turda doğru yazmalı.
- **Öneri:** Extraction'da bir "bütün ürünler" değeri (örneğin `offer_product_number = 0`) olsun. `check_offer` aynı tarih ve tutar türüyle her ürünü tek turda kontrol etsin ve yalnızca geçmeyenler için konuşsun. Bu PUB-13 akışını da kısaltır: kart tamam; kredi için son tarih önerilir.

### 4. ORTA: A+B spec'leri F-044 öncesi; ürünler numarayla anılıyor

- **Durum:** Üç A+B spec'inde de `product_kind_field`/`product_label_field` yok. Bu yüzden kontrol cümlesi ve okuma "the first product", "the second product" diyor ("credit card ending 2288" değil).
- **Fixture B (güncel biçim):** "personal loan", "car loan" diyor.
- **Policy riski:** Kontrol "all three products stated…" ve Brief B "name each product in words".
- **Öneri:** Güncel prompt'larla taze bir A+B extraction'ı (canlı model çağrısı, CTO onayı) ve kayıtlı fixture'ın yenilenmesi. Sürüm 13 Brief A spec'inde bu alanlar var, yani extraction artık yazıyor.

### 5. ORTA: Her sözden sonra `confirm_record`'a dönüş okumayı tekrarlatabilir

- **Akış:** Üç ürün için `confirm_record` → `confirmation_progress` → `confirm_record` döngüsü üç tur; sistem prompt'u "Call at most one tool per message" diyor.
- **Sorun:** Görev metni her girişte "Read these back … and ask for a clear confirmation" diyor. Model ikinci ve üçüncü girişte okumayı ve onay sorusunu tekrarlarsa PUB-11 kontrolü ("one read-back and one confirmation for all three") kaçar.
- **Kod tarafı:** Ledger tarafı doğru; kanca değerleri kabul edilen tekliflerden dolduruyor.
- **Öneri:** Prompt'a "if the customer already confirmed, call the promise tool for the next product without reading back again" eklenebilir. Daha sağlamı: onaydan sonra kayıt döngüsünü kod yürütsün (sessiz `api_request`'ler ve koddan gelen ürün numarası).

### 6. DÜŞÜK: Kancaya uydurma ürün numarası

Çok üründe kabul edilmemiş bir numara gelirse kanca gövdeyi doldurmuyor. Banka eksik alanlı çağrıyı reddediyor ve `confirmation_progress` yeniden deniyor. Yanlış bir söz kaydedilmiyor (test `test_promise_hook_with_a_number_that_was_not_accepted`). Sorun yok; yalnızca kayıt.

## Kodda doğrulananlar (sorun yok)

- **Tarih çözümü kodda:** "this Friday", "tomorrow" ve "30 October" doğru günlere çözülüyor (14 Ekim'den).
- **Bant ve son tarih:** Ürün başına doğru: kart erken bant, son tarih 2 Kasım; kredi geç bant, 23 Ekim.
- **Tutar:** Yalnız tarih tam tutarı alıyor; ürün geçişinde tutar türü `full`'a dönüyor (T-009c fix).
- **Okuma:** İki farklı tarihi de söylüyor (PUB-13 kontrolü). Ürün numarası köşeli parantezde ve yalnız araç için.
- **Sonuç:** Kayıtlı söz varsa `promise` (kapanış tablosu), üç vakada da.
- **Platform:** Tipli değişkenlere geçersiz yazma yok (F-060 sonrası).

## Testler (`tests/test_multi_ready.py`)

1. `test_pub11_three_products_one_date`: dört spec, ledger ve `promise`.
2. `test_pub11_one_turn_for_all_three_still_needs_two_more_turns`: bulgu 3 kaydı.
3. `test_pub13_one_date_after_the_loan_deadline`: dört spec, `date_too_late` → "yes" → ledger, okumada iki tarih.
4. `test_pub12_promise_then_refusals_reach_the_promise_and_outcome`: dört spec, söz ve `promise`.
5. `test_pub12_refused_products_are_noted`: **`expectedFailure`**, bulgu 1.
6. `test_refusal_of_one_product_skips_the_products_after_it`: bulgu 2 kaydı.
7. `test_promise_hook_with_a_number_that_was_not_accepted`: bulgu 6.

## Önerilen sıra

1. **Bulgu 1 ve 2 birlikte:** Ürün başına kod sahipli ret ve not durumu, kapanıştan önce bir `add_note` döngüsü. PUB-12 bunsuz geçemez.
2. **Bulgu 4:** Taze bir A+B extraction'ı (canlı, onay gerekli).
3. **Bulgu 5:** Prompt cümlesi ya da kod kayıt döngüsü.
4. **Bulgu 3:** "Bütün ürünler" kontrolü.

**UAT:** `docs/` dışında kaldım. Önerilen yeni kayıtlar: "Brief B notes have no step (rule 8, rule 11)" (YÜKSEK) ve "one product's refusal ends the negotiation" (ORTA). Durum: open.
