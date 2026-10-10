# F-051 review (yalnız tarihle `check_offer`, `offer_proposed_kind`, negotiate prompt'u, enum reddi)

Rapor: tasks/F-051-report.md; bulgu docs/UAT-FINDINGS.md F-051. Kod düzenlemedim, Freya ve modele istek atmadım. `python3 -m unittest`: 255 test geçiyor. PUB-07 akışını canlı Brief A spec'iyle (`traces/brief-a.spec.json`) üretilmiş `offer_setup`/`check_offer` kodunu çalıştırarak simüle ettim (bugün 2026-10-14, kredi, `days_late` 5, borç 540, taksit 180).

## Karar: merge edilebilir (iki orta notla)
Ana düzeltme çalışıyor: yalnız tarih artık `check_offer`'ı çalıştırıyor, tutar sırası doğru, model sınır uydurmuyor, enum reddi giderilmiş. İki zayıflık canlıda ilk Brief B / kabul-cümlesi vakasında çıkabilir (bulgu 1, 2); final koşudan önce düzeltilmeli.

## PUB-07 simülasyonu (beklenen: 540, 2026-10-27)
| Tur | Müşteri | `offer_date` | `check_offer` | Sonuç |
|---|---|---|---|---|
| A | "bugün ödeyemem" | boş | **çalışmaz** | `verdict none`, "No offer has been checked yet." |
| B | "the week after next" | "the week after next" | çalışır | `missing` (gün adı olmayan belirsiz dönem) |
| C | "Monday the 26th" | "Monday the 26th" | çalışır | **`date_not_business_day`, öneri 2026-10-27** (26 Ekim tatili) |
| D | "the 27th works" | "the 27th" | çalışır | **`ok`, `ready`, kabul: ürün p1, 2026-10-27, 540.0** |

`offer_setup` bilgi satırı: `Earliest 2026-10-14; latest date Monday 2026-11-02` (12. iş günü, 26 Ekim tatili atlanarak, doğru); taban 180, azami 540. Yani tam beklenen söz (`p1`, 540, 2026-10-27) üretiliyor.

## Kontrol listesi
| Kontrol | Sonuç |
|---|---|
| Yalnız tarihle `check_offer`'a geçiş | **Evet.** `negotiate → check_offer` koşulu yalnızca `offer_date` dolu ve boş değil; tutar şartı kalkmış (üretilen geçişte doğruladım). Tarih boşken yönlenmez (tur A). |
| `offer_proposed_kind` (full varsayılan) | **Evet.** `offer_setup` `full` yazıyor (`offer_amount_kind` = `none`, `offer_proposed_kind` = `full`; ikisi de enum içinde). |
| Taban önerisinden sonra minimum | **Evet.** Taban altı 100 → `amount_too_low`, `proposed = minimum`; sonra yalnız tarih → kabul, tutar **180** (taban). Fazla tutar 600 → `amount_too_high`, `proposed = full`. Ajan konuşmada tabanı önerdi (`proposed = minimum`) + yalnız tarih → 180. |
| Tutar sırası | **Doğru.** Müşterinin sayısı (250, tür `minimum` olsa bile 250) > müşterinin türü (`minimum` → 180) > önerilen tür; `other` ve sayı yok → `missing`. |
| Geç tarih | Yalnız tarih 2026-12-01 → kodla `date_too_late` (model uydurmuyor). |
| Negotiate prompt'u | **Doğru.** "The bank system checks every date and amount the customer names." "Verdict none: propose or ask, but never say whether a date or an amount is allowed." "Never state a limit yourself; say one only when the last offer check names it." "Never mention internal step, tool or variable names, and never write code." "If the customer names only a date, the amount you last proposed applies." Eski "verdict ok değilse mesajı söyle" kuralı "neither ok nor none" olmuş (başlangıçta "No offer has been checked yet." söyletmiyor). Ürünler "account facts'teki adla, liste numarasıyla değil". |
| `offer_setup` enum reddi | **Giderildi.** Hem `offer_setup` hem `check_offer` `offer_amount_kind`'a `''` yerine `none` yazıyor (enum `[full, minimum, other, none]`), her kontrolden sonra `'none'`; `offer_proposed_kind` yalnızca `full`/`minimum`. |

## Bulgular

### 1. [Orta] `offer_proposed_kind` ürün değişince sıfırlanmıyor (çok ürünlü akışta yanlış tutar)
- Denedim (Brief B fixture, kart + kredi): ürün 1'de taban altı teklif → `proposed = minimum`; yalnız tarihle taban kabul → `proposed` hâlâ `minimum`; ürün 2'de yalnız tarih → kabul edilen tutar **150** (kredi tabanı), tam tutar 300 değil. Ajan ürün 2 için tam tutarı önerse bile, çıkarım şeması "yeni öneri yoksa önceki değeri koru" dediği için eski `minimum` kalabilir; ledger'da yanlış tutar = vaka kaybı.
- **Düzeltme:** `check_offer` bir ürün için `ok` döndürünce (ve `more` ilerlemesinde) `offer_proposed_kind`'ı `full`'a döndür; extraction açıklaması yeni üründe yeniden başlatmayı anlatsın.

### 2. [Orta, TO-CONFIRM] Kabul cümlesinde tarih yoksa teklif kabul edilmiyor
- `offer_date` açıklaması "Copy the payment date phrase from the customer's last message". PUB-07 komut dizisi "Accepts the next business day when it is offered" der. Müşteri "Yes, that works" derse (tarih yok) `offer_date` boş kalır, `check_offer` çalışmaz, `offers_accepted_count` 0 kalır ve `confirm_record`'a geçiş (kabul sayısı > 0 şartı) olmaz; canlı v12'de müşteri "the 27th works" demişti (tarih içeriyor, tur D'deki gibi çalışır). Kabul cümlesi tarihsiz gelirse takılma riski var.
- **Düzeltme:** `offer_date` açıklamasına "If the customer accepts a date the agent just proposed, give that date" eklemek ve ek olarak verdict öneri taşıyorsa (`offer_suggested_date` dolu) tarihsiz kabulde bu önerinin kullanılması.

### 3. [Düşük] `missing` mesajı "date and amount" istiyor
- Tur B'de `missing` mesajı: "The date or the amount was not clear. Ask the customer for the exact date and amount." Artık tutar zorunlu değil ve brief "ajan her tutarı önerir, müşteriye ne kadar ödeyebileceğini sorma" diyor; `missing` yalnızca tarih çözülemediğinde (veya `other` ve sayı yokken) çıkıyor. İfade "Ask the customer for the exact date" (tutar eksikse ayrı cümle) olmalı; yoksa model tutarı sorabilir ve kuralı çiğner.

## Rapordaki açık risk (sizin kararınız)
`opening_unclear` adımının `who_answered`'ı ve `check_offer`'ın niyet değişkenlerini `''` ile sıfırlaması aynı enum reddine takılıyor olabilir. Kabul: yalnızca bir `none` çerçeve değeri eklemek yeterli; çok ürünlü akışta eski `agreed_date_and_amount` niyeti ikinci ürün konuşulmadan onaya geçirebilir. Ayrı küçük bir görev olarak öneriye katılıyorum (Brief B'den önce).

## Kurallar
Brief değeri yok (yeni sözcükler genel: `full`, `minimum`, `none`); sızıntı testi yeşil; stdlib, Freya/model isteği yok. UAT'ta F-051 durumu güncellenmemiş (önerilen: fixed offline, retest pending).

## Canlı doğrulama için
Raporun listesi doğru; ek olarak PUB-07'de tarihsiz kabul cümlesi ("Yes, that works") ve çok ürünlü vakada ikinci ürünün tutarı.
