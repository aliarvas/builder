# F-051 raporu: yalnız tarih söyleyen müşteri de kontrol ediliyor; model sınır uydurmuyor

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11

## Özet

- **Testler:** `python3 -m unittest` 255 testin hepsini geçiyor; 10'u yeni (`tests/test_offer_date_only.py`). `docs/PROMPTS.md` yeniden üretildi.
- **Değişen dosyalar:**
  - Kod: `builder/offer_check.py`, `builder/workflow.py`, `builder/prompts.py`.
  - Testler: `tests/test_multi_step.py` (üç beklenti, yeni davranışa göre).
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.
- **Dokunulmayanlar:** `selftest.py` ve `docs/` (PROMPTS.md hariç). UAT'taki F-051 durumunu güncellemedim; önerilen durum "fixed offline, retest pending".

## (1) Tarih yeterli; tutar ajanın son önerisinden

- **Yönlendirme:** `negotiate` → `check_offer` geçişi artık yalnızca `offer_date` dolu ve boş değilse tetikleniyor. Tutar ya da tutar türü şartı kalktı.
- **Yeni durum değişkeni `offer_proposed_kind`** (`full | minimum`), ajanın en son önerdiği tutar türünü tutuyor. Üç yerden yazılıyor:
  - **`offer_setup`:** başlangıçta `full` yazıyor; ajan önce tam tutarı istiyor.
  - **`check_offer`:** kod bir tutar önerince güncelliyor: taban altı teklifte (`amount_too_low`, tabanı öneriyor) `minimum`, fazla tutarda (`amount_too_high`) `full`.
  - **Extraction (`negotiate` şeması):** Yeni alan: "ajanın konuşmada en son önerdiği tutar: tam ya da taban; yeni öneri yoksa önceki değer kalsın". Extraction son mesajları gördüğü için (kit: "recent conversation messages"), ajanın konuşmada tabanı kendi önermesi de buraya düşüyor.
- **`check_offer`'da tutar sırası:**
  1. Müşterinin söylediği sayı.
  2. Müşterinin söylediği tür (`full` ya da `minimum`).
  3. Müşteri hiç tutar söylemediyse `offer_proposed_kind` (yoksa `full`).

  Müşteri "başka bir tutar" deyip (`other`) sayı vermediyse sonuç `missing`; ajan tutarı soruyor.
- **Sayıyı kod dolduruyor:** tam tutar için ürünün azami tutarı, taban için asgari tutar. Ardından tarih ve tutarın bütün kontrolleri normal çalışıyor; son tarihten sonraki bir tarih de böylece kodla `date_too_late` oluyor.

## (2) Negotiate prompt'u sınır uydurmuyor, iç adları anmıyor

`NEGOTIATION_TASK_TEMPLATE` yeniden yazıldı ve kısaltıldı:

- **Kontrol kodda:** "The bank system checks every date and amount the customer names."
- **Verdict yokken:** "Verdict none: propose or ask, but never say whether a date or an amount is allowed."
- **Kendi sınırını söylememe:** "Never state a limit yourself; say one only when the last offer check names it."
- **İç adlar:** "Never mention internal step, tool or variable names, and never write code." F-051'deki `_call:check_offer{…}` metnine karşı.
- **Yalnız tarih:** "If the customer names only a date, the amount you last proposed applies."
- **Ek düzeltme:** Eski "verdict ok değilse kontrol mesajını söyle" kuralı başlangıçta da tetikleniyordu. O anda verdict `none`, mesaj "No offer has been checked yet." idi ve model bunu söylemeye yönlendiriliyordu. Kural artık "Verdict neither ok nor none".
- **F-044 ile uyum:** Ürünler "account facts'teki adla, asla liste numarasıyla değil" anılıyor.
- **Uzunluk:** Şablon kısaltıldı. Sürüm 11 spec'inde `negotiate` 1175 token (önce 1117; hedef 1200), etiketli A+B'de 1313.

## (3) `offer_amount_kind` enum hatası

- `offer_setup` ve `check_offer` bu değişkene `''` yazıyordu. Platform enum dışı değeri reddediyor ("rejected by schema validation"); yani sıfırlama hiç gerçekleşmiyordu.
- Enum'a geçerli bir `none` değeri eklendi (`AMOUNT_KIND_NONE`). İki kod adımı artık `''` yerine `none` yazıyor.
- Extraction açıklaması da "müşteri tutar söylemediyse none" diyor.
- `offer_proposed_kind` yalnızca enum değerleriyle (`full`, `minimum`) yazılıyor.

## Testler (`tests/test_offer_date_only.py`)

- **Yönlendirme:** Yalnızca tarih `check_offer`'a gidiyor; boş ya da yok tarih gitmiyor.
- **Yalnız tarih, varsayılan:** Kart için tam tutar (95) kabul ediliyor.
- **Taban önerisinden sonra yalnız tarih:** Müşteri tabanın altında tutar söylüyor → kod tabanı öneriyor ve `offer_proposed_kind = minimum` oluyor → müşteri yalnızca tarih söylüyor → taban (28.5) kabul ediliyor.
- **Ajan tabanı konuşmada önerdiyse** (extraction `minimum`): Yalnız tarih tabanı alıyor.
- **Öncelik:** Müşterinin sayısı ya da türü öneriye karşı kazanıyor.
- **Eksik tutar:** `other` ve sayı yoksa `missing`.
- **Geç tarih:** Yalnız tarih, son tarihten sonraysa kodla `date_too_late` oluyor ve doğru son tarih öneriliyor (model uydurmuyor).
- **Enum:** `offer_amount_kind` kurulumdan ve kontrolden sonra enum içinde (`none` dahil); kod `''` yazmıyor; `offer_proposed_kind` enum içinde.
- **Prompt:** Yeni kurallar şablonda.
- **Güncellenen `test_multi_step.py` beklentileri:**
  - "yalnız tarih" tablo satırı artık `missing` değil `ok`;
  - yönlendirme testi tutar şartının kalktığını doğruluyor;
  - "tek tarihte ödeyememe ret değildir" ifadesi yeni metne göre.

## Aynı türden açık risk (kararınız)

Platform enum dışı değeri reddediyorsa aynı sorun iki yerde daha var. `''` yazılan ama enum'lu extraction değişkenleri:

1. `opening_unclear` adımı `who_answered` değişkenini `''` ile temizliyor.
2. `check_offer` pazarlık ve onay niyet değişkenlerini `''` ile sıfırlıyor (`reset_variables`).

Sıfırlama sessizce başarısız olursa eski niyet kalır. Örneğin çok ürünlü akışta eski bir "proposal" niyeti ve kabul edilmiş bir teklif, ikinci ürün konuşulmadan onay adımına geçirebilir. Çözüm burada yapılanla aynı: enum'lara bir çerçeve değeri (`none`) ekleyip onu yazmak. Bu, extraction'ın gördüğü değer listelerini değiştirdiği için ayrı küçük bir görev olarak öneriyorum; bu görevde yapmadım.

## Canlı tekrar (CTO)

**PUB-07 (müşteri yalnızca tarih söylüyor):**
- `check_offer` her tarihte çalışıyor mu (trace'te `offer_verdict`)?
- Kabul edilen tutar ajanın önerdiği tutar mı?
- Ajan kendi başına "son tarih şu" diyor mu?
- `_call:` ya da benzeri bir iç metin müşteriye gidiyor mu?
- "rejected by schema validation" uyarısı kayboldu mu?
