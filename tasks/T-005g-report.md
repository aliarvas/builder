# T-005g raporu: weekday politikası ve ürün-bantlı teklif limiti

**Geliştirici:** codex-dev · **Tarih:** 2026-10-10

## Sonuç

Canlı Brief A extraction'ında görülen iki spec kaybı renderer tarafında giderildi:

1. `next <weekday>` yorumu artık spec verisiyle seçiliyor; tanımlı Brief A/B fixture'ları soru sormadan takip eden takvim haftasını kullanıyor.
2. Reddedilen teklif limiti ürün koşullarına göre seçilebiliyor ve çok ürünlü akışta sayaçlar ürün başına tutuluyor.

Freya isteği yapılmadı, `env.sh` okunmadı ve commit atılmadı. `builder/extract.py`, `builder/llm.py` ve extraction prompt'ları değiştirilmedi. Builder içine Brief A'ya özgü tarih, band veya sayı yazılmadı; bütün değerler fixture/spec verisi olarak kaldı.

## Spec sözleşmesi

### `offer.next_weekday`

İsteğe bağlı enum alanı:

- `following_week`: `next <weekday>`, sonraki takvim haftasının o günü;
- `upcoming`: sıradaki gelecek occurrence;
- `ask`: aynı takvim haftasına düşen belirsiz kullanımda onay sorusu.

Alan yoksa geriye uyumlu varsayılan `ask`. `this <weekday>` her durumda mevcut takvim haftasının günü olarak çözülüyor; geçmişteyse normal `date_too_early` kontrolünden geçiyor.

### `offer.max_rejected_offers_by_product`

İsteğe bağlı, sıralı kural listesi:

```json
{
  "when": [{"field": "<product field>", "min": 1, "max": 7}],
  "value": 1
}
```

Koşullar mevcut offer `when` biçimini kullanıyor ve ilk eşleşme kazanıyor. Eşleşme yoksa mevcut scalar `max_rejected_offers` fallback olarak kullanılıyor. Böylece eski spec'ler değişmeden çalışıyor.

## Renderer davranışı

- `resolve_offer_day` doğrudan `next_weekday` politikasını okuyor.
- `ask` dışındaki politikalarda `date_ambiguous` üretilmiyor.
- Rejection limiti seçili ürün üzerinden hesaplanıyor.
- Distinct teklif imzaları ve sayaçlar ürün numarasına göre ayrı saklanıyor; bir üründeki ret başka ürünün limitini tüketmiyor.
- Eski `offer_rejections` ve `offer_last_signature` değişkenleri mevcut ürünün son durumunu göstermeye devam ediyor.
- `check_offer` zaten `offer_progress=limit` ürettiği için `workflow.py` içindeki mevcut `check_offer → closing` yolu yeni seçilen limiti ek değişiklik olmadan uyguluyor.

## Fixture ve testler

- Brief A ve Brief B fixture'larında `next_weekday=following_week` tanımlandı.
- Aynı fixture'larda `days_late` 1–7 için limit 1, 8–45 için limit 2 kuralı eklendi; scalar fallback 2.
- Sentetik fixture yeni alanları taşımıyor; böylece `ask` ve scalar fallback geriye uyumluluğunu test ediyor.
- Recorded extraction cevabı ve bağımsız reference snapshot yeni spec şekline taşındı; extraction kodu/prompt'u değiştirilmedi.
- Testler şunları kapsıyor:
  - `following_week`, `upcoming` ve varsayılan `ask`;
  - mevcut haftadaki geçmiş bir `this <weekday>`;
  - early/late band limitleri;
  - duplicate teklifin yeniden sayılmaması;
  - çok ürünlü sayaç izolasyonu;
  - scalar fallback;
  - enum, pozitif limit ve `when` doğrulama hataları.

## Doğrulama

- `python3 -m py_compile builder/spec.py builder/offer_check.py builder/workflow.py tests/test_multi_step.py` — geçti.
- `python3 -m unittest` — **140/140 geçti**.
- Değişen bütün JSON fixture'larında `python3 -m json.tool` — geçti.
- `git diff --check` — geçti.

İlk tam koşudaki stale extraction fixture göçü F-039 olarak `docs/UAT-FINDINGS.md` içine kaydedildi ve düzeltildi.

## Fix — review düzeltmeleri

`reviews/T-005g-review.md` sonrasında iki zorunlu bulgu kapatıldı. Bu bölüm yukarıdaki ilk uygulama notlarında geçen 1/2 band değerlerinin ve doğrudan `check_offer → closing` anlatımının yerini alır.

### Bulgu 1 — invalid offer ile persuasion ayrımı

- `max_rejected_offers` ve `max_rejected_offers_by_product`, yalnız deterministik tarih/tutar kurallarını geçemeyen distinct müşteri tekliflerini sayar.
- Düz ret sonrasındaki persuasion attempt sayısı bu alan değildir; negotiation intent ve brief'ten gelen konuşma kurallarıyla ayrı kalır.
- `spec.py` açıklaması bu ayrımı ve en az bir karşı öneri hakkını açıkça tanımlar.
- Scalar ve koşullu limit değerleri artık en az 2 olmak zorunda.
- Brief A/B ile recorded extraction fixture'larında early/late değerleri 2/3 oldu: ilk geçersiz teklif karşı öneriyi üretir; ancak karşı önerinin ayrı bir teklifle reddedilmesinden sonra ürün tükenebilir.
- `tests/briefs/raw-a/reference-spec.json` aynı 2/3 anlamına; `tests/briefs/changed-a/reference-spec.json` ise 3/2/3 değerlerine güncellendi.
- Test, erken bantta son tarih sonrası ilk tarihin `date_too_late` kaldığını, deadline önerisini verdiğini ve `offer_progress=rejected` üreterek agent'a karşı öneriyi söyleme turu bıraktığını doğruluyor.

### Bulgu 2 — ürün bazında limit dolumu

- Bir ürün limiti doldurduğunda ürün numarası `offers_noted` içine ekleniyor.
- İşlenmemiş ürün varsa `offer_progress=more`; workflow mevcut fallback yoluyla negotiation'a dönüyor.
- Tüm ürünler işlendiyse ve en az bir kabul edilmiş teklif varsa `ready`; workflow `confirm_record` yoluna gidip kabul edilmiş teklifleri kaydediyor.
- Tüm ürünler yalnız tükenmiş/noted durumdaysa son üründe `limit`; ancak o zaman closing yolu çalışıyor.
- İki ürünlü Brief B testleri hem “ilk ürün tükenir, ikinci ürün kabul edilir” yolunu hem de “iki ürün de tükenir, yalnız son üründe kapanır” yolunu kapsıyor.

Düzeltme sonrası `python3 -m unittest` **142/142** geçti. `py_compile`, değişen JSON fixture doğrulamaları ve `git diff --check` de geçti. Freya isteği yapılmadı; commit atılmadı; `env.sh`, `builder/extract.py` ve `builder/llm.py` değiştirilmedi.
