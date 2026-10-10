# F-060 raporu: `offer_amount` geçerli bir float ile sıfırlanıyor; "exact day" sorusu

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11 · **Kaynak:** `tasks/LIVE-AUDIT-report.md` F-060 ve bulgu "did not catch" (LOW)

## Özet

- **Testler:**
  - Yeni dosya `tests/test_offer_amount_reset.py`: 5 test.
  - Benim alanımdaki bütün testler geçiyor: `test_offer_amount_reset`, `test_offer_date_only`, `test_offer_speech`, `test_spoken_output`, `test_prompt_budget`, `test_vertical_slice`, `test_multi_step.OfferCheckTests`.
  - Tam koşuda (327 test) 5 kırılma var. Hepsi özel yol/transfer şekli testleri (örneğin `test_special_path_shapes_follow_the_tool`: `'tts' != 'silent'`). Bu claude-dev2'nin `workflow.py`'de süren F-059 işi (dosya 02:13'te değişti). Bu görevde `workflow.py`'ye dokunmadım.
- `docs/PROMPTS.md` yeniden üretildi.
- **Değişen dosyalar:**
  - Kod: `builder/offer_check.py`, `builder/prompts.py` (yalnız `missing` cümlesi).
  - Testler: `tests/test_multi_step.py` (bir yardımcı beklenti), `tests/test_offer_date_only.py` (bir beklenti).
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.

## Önce kanıt (offline)

- **`PlatformCall` (yeni test yardımcısı):** Platform kuralını taklit ediyor (F-052'de canlıda görüldü): bir kod adımı tipli bir extraction değişkenine tipine uymayan bir değer yazarsa yazma reddediliyor ve eski değer kalıyor. Kurallar extraction şemasından geliyor: float, integer, boolean, enum.
- **Düzeltmeden önceki sonuç:**
  - Her `check_offer` koşusunda `('check_offer', 'offer_amount', '')` reddi.
  - **Eski tutar senaryosu:**
    1. Müşteri kart için 10 öneriyor (taban 28.50); kod `amount_too_low` ile tabanı öneriyor ve `offer_proposed_kind = minimum` oluyor.
    2. Sıfırlama reddedildiği için `offer_amount` 10 olarak kalıyor.
    3. Müşteri yalnızca tarih söylüyor. Kod eski 10'u okuyor ve yine `amount_too_low` diyor; doğrusu 28.50 ile `ok`.

  Bu, canlıda müşteriye aynı tabanı ikinci kez söyletir ve geçersiz teklif sayacını haksız yere artırır.

## Düzeltme

- **Sentinel:** `check_offer` artık `offer_amount`'u `""` ile değil, `AMOUNT_NONE_VALUE = -1.0` ile sıfırlıyor. Bu geçerli bir float; platform kabul ediyor.
- **Okuma:** `parse_amount` negatif bir sayıyı "tutar yok" sayıyor. Hiçbir müşteri tutarı negatif olamaz.
- **Metin yolu:** Platform değeri koda metin olarak verirse (`"-1.0"`, `"-1"`) de "tutar yok" sayılıyor. Eski kod eksi işaretini atıp 1.0 okurdu.
- **Neden sentinel, neden "tutar turu" işareti değil:** Bir işaret, müşterinin aynı tutarı yeni bir tarihle tekrar etmesini eski değerden ayıramazdı. Sentinel her kontrolden sonra değişkeni gerçekten boşaltıyor; extraction yalnızca müşteri yeni bir tutar söylediğinde yazıyor.

## LOW: "did not catch the date"

- **Yeni `missing` cümlesi (genel):** "Could you tell me the exact day you would like to pay?"
  - Müşteri bir dönem söylediğinde ("the week after next") yanlış değil: "duymadım" demiyor, yalnızca kesin günü istiyor.
  - Anlaşılmayan bir cevaba da uyuyor.
  - Konuşma dedektörüne göre müşteriye söylenen bir cümle (F-047).

## Testler (`tests/test_offer_amount_reset.py`)

1. **Reddedilen yazma yok:** Üç turluk çok ürünlü akışta hiçbir tipli değişkene geçersiz değer yazılmıyor.
2. **Eski tutar:** 10'dan sonra yalnızca tarih → taban (28.50) ile `ok`.
3. **Yeni tutar sayılıyor:** 10'dan sonra 120 → `amount_too_high`.
4. **Sentinel okuması:** Sıfırlamadan sonra değişken `-1.0`; `-1.0`, `"-1.0"` ve `"-1"` "tutar yok" sayılıyor ve önerilen tam tutar (95) geçiyor.
5. **Dönem cevabı:** "the week after next", "sometime next month" ve anlaşılmayan bir cevap `missing` veriyor; cümle "exact day" diyor ve "did not catch" geçmiyor.

**Güncellenen beklentiler:**
- `test_multi_step.assertVerdict`: kontrolden sonra `offer_amount` artık `""` değil `-1.0` (22 alt test aynı yardımcıyı kullanıyor).
- `test_offer_date_only`: yeni `missing` cümlesi.

## Riskler

- **[HYPOTHESIS] Değer müşteriye gitmez:** `-1.0` yalnızca kodun okuduğu bir değişkende. Prompt'larda `{{offer_amount}}` yok; özetler ve mesajlar kabul edilmiş tekliflerden yazılıyor.
- **[HYPOTHESIS] Extraction'ın davranışı:** Extraction değişkenin mevcut değerini görüyorsa `-1`'i kopyalayabilir; bu zararsız, çünkü "tutar yok" sayılıyor. Canlıda doğrulanmalı.
- **Kapsam:** Kod adımlarının yazdığı diğer tipli değişkenler (`offer_product_number` integer, `agreed_product_count` integer) kod tarafından `""` ile yazılmıyor. Test bunu yalnız teklif akışı için kanıtlıyor.

## UAT

`docs/` dışında kaldım. Önerilen durum: "F-060: fixed offline (sentinel -1.0), retest pending". LOW metin bulgusu: "fixed offline".

## Canlı tekrar (CTO)

- **`check_offer` adımı:** trace'te `offer_amount` için `validation_errors` kayboldu mu?
- **PUB-07 benzeri:** Müşteri tabanın altında bir tutar söylüyor, sonra yalnızca tarih veriyor; taban ile kabul ediliyor mu?
- **"The week after next":** Ajan "exact day" diye mi soruyor?

## Fix (review F-060: bulgu 1, ret imzası)

- **Sorun:** Ret imzası ham değişkenden kuruluyordu. İlk turda `offer_amount` yoktu (`None`), sonraki turlarda sentinel vardı (`-1.0`). Bu yüzden aynı yalnız-tarih geçersiz teklif ikinci kez yeni bir ret sayılıyordu; sınır (2) doluyor ve ürün kapanıyordu.
- **Düzeltme (`offer_check.py`):** İmza artık parse edilmiş tekliften kuruluyor: ürün numarası, gün (ISO) ve tutar.
  - Tutar, `parse_amount` sonucu ve yalnız tarihte önerilen tutar kuralından sonraki değer.
  - Bu yüzden `""`, `None`, `-1.0`, `"-1"` ve aynı günün başka yazımı aynı teklif sayılıyor.
  - Tutar türü imzadan çıktı. Aynı sıfırlama sorununu taşıyordu ve bilgisi tutarda zaten var.
- **Testler (`tests/test_offer_amount_reset.py`, `RejectionSignatureTests`, 2 yeni):**
  - İki aynı yalnız-tarih geçersiz teklif (`2026-11-30`): sentinel gerçekten yazılıyor, sayaç 1'de kalıyor, ürün kapanmıyor (`more` yok, `offers_noted` boş).
  - Önce "95 ile 30 Kasım", sonra yalnızca "30 Kasım" (tam tutar 95) aynı teklif ve sayaç 1. Farklı bir gün yeni teklif ve sayaç 2.
- **Sonuç:** `python3 -m unittest` 337 testin hepsini geçiyor; claude-dev2'nin F-056/059 işi bittiği için tam koşu temiz. Prompt metni değişmedi. `workflow.py`'ye dokunulmadı.

Freya yok, commit yok, `env.sh` yok.
