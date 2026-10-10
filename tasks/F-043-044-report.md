# F-043 / F-044 raporu: bekleme cümlesi ve insan dostu geri okuma

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

- **Testler:** `python3 -m unittest` 223 testin hepsini geçiyor. Yeni testler `tests/test_spoken_output.py` (9) ve `tests/test_extract.py` (+1). Sızıntı testi yeşil. `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.
- **Dokunulmayanlar:** `tools/submission_check.py`, `run_trace.py` ve `build.py`. Çalışma ağacında başkasının commit edilmemiş değişiklikleri duruyor.

**Değişen dosyalar:**

- Kod: `builder/workflow.py`, `builder/offer_check.py`, `builder/prompts.py`, `builder/spec.py`, `builder/extract.py`.
- Fixture'lar:
  - `tests/fixtures/spec-brief-a.json` ve `spec-brief-b.json`: iki adlandırma alanı (B'nin tek satırlık biçimi korundu);
  - `tests/fixtures/extract/brief-a-replies.json`.
- Testler: `tests/test_multi_step.py` (özet beklentisi).
- Doküman: `docs/UAT-FINDINGS.md`.

## F-043: bekleme cümlesi

- **Ne değişti:** Hesap adımı (`account`, doğrulamadan sonraki ilk passthrough adımı; API beklemesi burada başlıyor) artık sessiz değil. `on_enter` olarak kısa sabit bir cümle söylüyor. Kit bunu açıkça izin veriyor: "a short fixed line that covers the wait".
- **Cümlenin kaynağı:**
  - Spec'te `agent.wait_line` varsa o kullanılıyor. Bu yeni ve isteğe bağlı bir alan; extraction onu çağrının dilinde, borç ayrıntısı içermeyen tek bir cümle olarak istiyor.
  - Yoksa builder'ın İngilizce varsayılanı kullanılıyor (`prompts.py`'de `ACCOUNT_WAIT_LINE`): "Thank you. One moment while I check your account."
- **Kapsam:** Yalnızca `account` adımı konuşuyor; `offer_setup` ve `check_offer` sessiz kalıyor. Böylece müşteri art arda iki sabit cümle duymuyor.
- **Yorumum:** Görevde "hesap adımından sonraki ilk passthrough adım" yazıyordu. Ben cümleyi hesap adımının kendisine koydum, çünkü F-043'teki öneri "doğrulamadan sonraki ilk passthrough adım" ve bekleme hesap API çağrısıyla başlıyor. `offer_setup`'a taşımak tek satırlık bir değişiklik.
- **TO-CONFIRM:** Platformun Türkçe dolgu cümlesinin kaybolup kaybolmadığı ancak chat'te görülür. Bu bizim koddan bağımsız bir platform davranışı.

## F-044: insan dostu geri okuma

**Spec ve extraction:** `account` bölümüne iki isteğe bağlı alan geldi.

- `product_kind_field`: ürün türü alanı, örneğin bir tür enum'u.
- `product_label_field`: müşterinin tanıdığı alan, örneğin son haneler.
- Extraction bunları istiyor. Kod, alanların hesap aracının ürün alanlarından biri (ya da `""`) olduğunu kontrol ediyor.

**Kod (`offer_check.py`):**

- **Ürün adı:** Tür kelimeye çevriliyor ve etiket ekleniyor: "credit card ending 0377". Etiketi olmayan ürünlerde yalnızca tür kalıyor ("personal loan"). Spec bu alanları vermiyorsa sıra sözcüğü kullanılıyor ("the first product"); tek üründe "the product".
- **Tarih:** "Friday, 16 October". Yıl yalnızca bu yıl değilse söyleniyor: "Monday, 4 January 2027".
- **Tutar:** Gereksiz ondalık yok: 420.00 → "420". 95.5 → "95.50" kalıyor.
- **Özet örneği:** `credit card ending 0377: 95.50 on Friday, 16 October [product number 1]`.
  - Ürün numarası promise aracının parametresi olduğu için kaldırılamaz. Köşeli parantezde duruyor.
  - Onay prompt'u (`CONFIRM_TASK_TEMPLATE`) şunu söylüyor: "The product number in square brackets is only for the promise tool: never say it to the customer". Geri okuma "exactly" yerine "in these words" yapılıyor.
- **Ürün bilgileri (`products_facts`):** Her ürün satırının sonuna "Name it to the customer as: credit card ending 0377." eklendi. Negotiate adımında da aynı ad kullanılıyor. Mevcut biçim ve "Product N" sayımı değişmedi; mevcut testler buna dayanıyordu.
- **Genellik:** Brief değeri yok. "ending", sıra sözcükleri ve ay/gün adları dile bağlı genel şablon parçaları; ay ve gün adları zaten kodda vardı.

## Testler

- **F-043:**
  - Hesap adımı varsayılan cümleyi `tts` olarak söylüyor, hâlâ passthrough, cümle kısa ve değişken içermiyor.
  - Spec'teki `wait_line` kazanıyor (boşlukları kırpılıyor); string olmayan değer `SpecError` veriyor.
  - Yalnızca hesap adımı konuşuyor.
- **F-044:**
  - Ad, konuşma dilinde tarih ve ondalıklı tutar doğru.
  - Özette "Product 1" ve ISO tarih yok.
  - Tam tutarda ondalık yok; başka yıl söyleniyor.
  - Adlandırma alanları yokken sıra sözcükleri kullanılıyor.
  - Facts satırları adı veriyor; iç id görünmüyor.
  - Onay prompt'u köşeli parantezdeki numarayı söyletmiyor.
  - Alan string değilse `SpecError`.
  - Extraction alanları taşıyor ve ürün alanı olmayan bir değeri reddediyor.
- **Değişen beklenti:** Brief B'deki iki ürünlü özet testi yeni biçime göre güncellendi.

## Canlı tekrar (CTO)

- **PUB-01 chat'inde bakılacaklar:**
  - Doğrulamadan sonra Türkçe dolgu yerine "Thank you. One moment while I check your account." duyuluyor mu?
  - Geri okuma "credit card ending …, 420 on Wednesday, 14 October" gibi mi; "Product 1" söylenmiyor mu?
- **Yeni extraction'da bakılacaklar:** `agent.wait_line`, `account.product_kind_field` ve `account.product_label_field` doldu mu? Bu alanlar boş kalırsa geri okuma "the first product" der; doğru ama daha az açık.
