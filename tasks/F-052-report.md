# F-052 raporu: F-051 review takibi ve enum sıfırlama

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11 · **Kaynak:** `reviews/F-051-review.md` bulgu 1–3 ve "Rapordaki açık risk"

## Özet

- **Testler:** `python3 -m unittest` 263 testin hepsini geçiyor; 8'i yeni (7'si `tests/test_offer_date_only.py`, 1'i `tests/test_extract.py`). `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.
- **Değişen dosyalar:**
  - Kod: `builder/offer_check.py`, `builder/workflow.py`, `builder/prompts.py`, `builder/spec.py`, `builder/extract.py`.
  - Testler: `tests/test_multi_step.py` (iki beklenti), `tests/test_offer_date_only.py`, `tests/test_extract.py`.

## Bulgu 1: önerilen tutar türü ürün başına

- `check_offer` bir ürün için `ok` dönünce `offer_proposed_kind` yeniden `full` oluyor. Sonraki ürün tam tutardan başlıyor.
- Extraction açıklaması: "şu an konuşulan ürün için ajanın en son önerdiği tutar; konuşma başka ürüne geçince, ajan o ürünün tabanını önermediyse `full`".
- Test: Review'daki senaryonun aynısı. Ürün 1'de taban altı teklifin ardından yalnız tarihle taban kabul ediliyor; ürün 2'de yalnız tarih **tam tutarı (300)** veriyor.

## Bulgu 2: tarihsiz kabul ("Yes, that works")

- **Yeni extraction alanı `offer_accepts_proposal`** (`yes | none`): "müşterinin son mesajı ajanın az önce önerdiği tarihi ve tutarı, tarih söylemeden kabul ediyorsa yes".
- **Yönlendirme:** `negotiate` → `check_offer` artık "tarih dolu **veya** `offer_accepts_proposal = yes`" ile tetikleniyor.
- **`check_offer`:** Tarih boşsa ve kabul `yes` ise son kontrolün önerdiği tarihi (`offer_suggested_date`) kullanıyor. Önerilmiş bir tarih yoksa sonuç `missing` ve ajan tarihi soruyor. Kontrolden sonra `offer_accepts_proposal` `none`'a dönüyor.
- **`offer_date` açıklaması:** "müşteri ajanın az önce önerdiği tarihi adını söylemeden kabul ederse tarihi ajanın söylediği gibi yaz". Bu, ajanın prompt'tan kendi önerdiği tarihler için de çalışıyor; örneğin ilk ikna denemesindeki hafta sonu tarihi.
- **Test:**
  - Son tarihten sonraki bir teklifte kod 2026-11-02'yi öneriyor; müşteri yalnızca "yes" diyor ve teklif 2026-11-02 ile `ok` oluyor.
  - Önerilmiş tarih yoksa "yes" tarihi sorduruyor.

## Bulgu 3: `missing` yalnızca tarih istiyor

- `missing`: "The date was not clear. Ask the customer for the exact date."
- **Yeni sonuç `amount_missing`:** Müşteri "başka bir tutar" deyip sayı vermediğinde çıkıyor: "The amount was not clear. Propose the amount again yourself: the full amount due, or the minimum if you offered it." Brief'e uygun olarak müşteriye "ne kadar ödeyebilirsiniz" sorulmuyor. Bu sonuç geçersiz teklif sayacına girmiyor.
- **Ek:** `ok` mesajı artık "product 1" değil, müşteriye görünen ürün adını söylüyor: "The offer for the credit card ending 0377 is valid and noted.". `product_unknown` da "by its number" demiyor (F-044 ile uyum).

## Açık risk: enum değişkenleri `''` ile değil `none` ile sıfırlanıyor

- **Yeni çerçeve değeri `FRAMEWORK_NONE_VALUE = "none"`** (`spec.py`). Platform enum dışı değeri reddettiği için `''` ile sıfırlama sessizce eski değeri bırakıyordu.
- **Bu değerle sıfırlanan değişkenler:**
  - `opening_unclear` adımında `who_answered`;
  - `check_offer`'da pazarlık ve onay niyet değişkenleri.

  `reset_variables` artık (değişken, değer) çiftleri taşıyor. Özel yol sonuç değişkenleri enum değil, araç cevabından eşleniyor; onlar `''` ile kalıyor.
- **Extraction:** `none` şu değişkenlerin enum'una eklendi: `who_answered`, üçüncü kişi niyeti, pazarlık niyeti, onay niyeti. Hiçbir geçiş `none` ile tetiklenmiyor. Pazarlık niyeti açıklaması "none'ı yalnız sistem yazar" diyor.
- **Ayrılmış değer:** `spec.py` `none`'ı bu değer listelerinde reddediyor; extraction da route değerlerinde (`greeting` gibi) reddediyor.
- **Çok ürünlü akış:** Ürün 1 kabul edildikten sonra (`more`) pazarlık niyeti `none` oluyor. Eski bir "proposal" niyeti ve kabul sayısı > 0, ikinci ürün konuşulmadan onay adımına geçiremiyor (testli).
- **Testler:**
  - Kontrolden sonra niyet, tutar türü, kabul ve önerilen tür değişkenlerinin hepsi kendi enum'unda.
  - `who_answered` sıfırlaması `none`.
  - Spec'te `none` dört listede de `SpecError` veriyor.
  - Extraction route değeri olarak `none`'ı onarıma gönderiyor.

## Canlı tekrar (CTO)

- **PUB-07:**
  - Müşteri önerilen tarihe yalnızca "yes" deyince teklif kabul ediliyor mu?
  - "rejected by schema validation" uyarısı yok mu?
- **Çok ürünlü vaka (Brief B):**
  - İkinci ürünün tutarı tam tutardan başlıyor mu?
  - İkinci ürün konuşulmadan onaya geçilmiyor mu?
- **Açılış:** Belirsiz cevaptan sonra `who_answered` `none` oluyor mu, yeniden sorma doğru çalışıyor mu?
