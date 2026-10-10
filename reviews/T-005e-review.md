# T-005e review (söz alma yolu düzeltmeleri, F-025..F-031)

Rapor: tasks/T-005e-report.md. Kod değiştirmedim, Freya'ya istek atmadım. 104 test geçiyor. Yöntem: `git diff` okuması ve üretilen `offer_setup` / `check_offer` kodunu Brief A fixture'ından `exec` ederek kendi girdilerimle çalıştırma (bugün = Çarşamba 2026-10-14).

## Karar: düzeltme gerekli
Bulgu 1 (ürün okuyucu gözlenen anahtarı okumuyor) F-028'i gerçek Freya'da aynen geri getirir; bulgu 2 (yanlış tarihle sessiz kabul) tek tek vakayı düşürür. İkisi de küçük düzeltme. Geri kalan F-025/F-027/F-029/F-030/F-031 değişiklikleri uygun.

## Bulgular (önem sırasıyla)

### 1. [Yüksek] Düz anahtar okuyucu `get_account_response.*` arıyor; chat'te gözlenen anahtar `account_response.*`
- `offer_check.py:46` `products_flat = "get_account_response.data." + products_field`; `load_products` yalnızca bu önekle başlayan anahtarları yeniden kuruyor (`offer_check.py` ~80–100). Aynı sabit `workflow.py:223` (ürün numarası hook'u) ve özel yol ilerlemesinde. F-028'in kendi kaydı gözlenen anahtarı `account_response.data.products.0.product_id` olarak yazıyor (düğüm adı `account`, kit `tools-and-code.md:483`: kod düğümü için de `<düğüm>_response.*`). Testler (`test_multi_step.py:248,772,1148`) kendi uydurdukları `get_account_response.*` ile geçiyor, gözlenen biçimi hiç kullanmıyor.
- Doğrulama: aynı Brief A `offer_setup` kodunu iki önekle çalıştırdım: `get_account_response.data.products.0.*` → `Product 1: type credit_card, ...` ; `account_response.data.products.0.*` → **`No products were returned.`** Yani chat'te gözlenen durumda F-028 aynen sürüyor (teklif `product_unknown`, F-025 id okuma riski geri gelir).
- **Düzeltme:** öneki sabit yazma. Anahtarı kalıpla ara: `^(?:[A-Za-z0-9_]+)_response\.data\.<products_field>\.(\d+)\.(.+)$` (tool adı ve düğüm adı ikisi de olabilir) ve ilk eşleşen öneki kullan; mevcut liste/JSON dizesi yedekleri dursun. `workflow.py:223` ve `special_noted_code` tarafında aynı ortak okuyucuyu kullan. Testlerde **gözlenen** `account_response.*` ve `get_account_response.*` biçimlerinin ikisi de bulunsun.

### 2. [Orta-Yüksek] "next week" ifadeleri bu haftaya çözülüp sessizce kabul ediliyor
Çözücü (`resolve_offer_day`) çıktıları, bugün Çarşamba 2026-10-14 için, el hesabımla karşılaştırıldı:

| İfade | Çözücü | Doğru | Not |
|---|---|---|---|
| today / tomorrow | 10-14 / 10-15 | aynı | doğru |
| this Friday | 10-16 | 10-16 | doğru |
| next Monday | 10-19 | 10-19 | doğru |
| Monday the week after next | 10-26 → tatil kayması: `date_not_business_day`, öneri 10-27 | aynı | doğru (Brief A tatili 26 Ekim) |
| the week after next Monday | aynı | aynı | doğru |
| Monday the 26th | 10-26 → kayma, öneri 10-27 | aynı | doğru |
| October 20 / 20 October / 20th of October | 10-20 | 10-20 | doğru |
| Friday the 16th, this/next Wednesday | 10-16, 10-14, 10-21 | aynı | doğru |
| **Friday next week** | **10-16 (ok)** | 10-23 | **yanlış, kabul ediliyor** |
| **next week Friday** | **10-16 (ok)** | 10-23 | **yanlış, kabul ediliyor** |
| Monday next week | 10-19 | 10-19 | tesadüfen doğru (`next monday` bulunmuyor, yine de bu haftanın ilk pazartesisi) |
| next Friday | 10-16 | belirsiz (10-16 veya 10-23) | bkz. aşağı |

- Neden: yalnızca `'next ' + <gün>` ve `week after next` kalıpları var; "next week" + gün adı hiçbir kalıba girmiyor, düz gün adına düşüyor ve yaklaşan aynı haftanın günü seçiliyor. Sonuç teklifin **yanlış tarihle `ok`** alınması: ledger'a yanlış söz tarihi yazılır (tamamen veya hiç puanlamada kritik).
- **Düzeltme:** metinde `next week` varsa ve `week after next` yoksa tarih = (haftanın bir sonraki pazartesisi) + gün farkı (gün adı yoksa çözme, `missing` dön). Belirsiz çözülemeyen ifadelerde yanlış tarih yerine `missing` daha güvenli: kural "emin değilsen `missing`".
- "next Friday" Çarşamba günü söylenirse insanlar sık sık 10-23 kasteder; çözücü 10-16 veriyor. Belirsizse (gün adı aynı haftaya düşüyorsa ve `next` var) ya bir doğrulama sorusu ürettir (`offer_message` "Do you mean Friday 16 October?") ya da kuralı brief'in ihtiyacına göre açıkça yaz; şu an sessiz.
- Çözülemeyen ifadeler `missing` dönüp tekrar soruyor, güvenli: `the 20th`, `on the 30th`, `Oct 20` (kısaltılmış ay), `10/20`, `the day after tomorrow`, `in two days`, `end of the month`, `the 26th`. Sık duyulanlar eklenebilir (yalnız gün numarası = bugünden itibaren o günü taşıyan ilk tarih; üç harfli ay; `day after tomorrow`), ama düşük öncelik.
- Tatil kayması ve hafta sonu doğru: Cumartesi → öneri Pazartesi 10-19; 10-26 tatili → 10-27.

### 3. [Orta] Refusal tanımı yalnızca açıklama; bir "karşı soru sayacı" yok
- Extraction açıklaması ve prompt "başka tarih sor; tek başına ret değil" diyor (`workflow.py` negotiation intent `description`, `NEGOTIATE` prompt). Doğru yönde, ama F-029 bir model davranışı; semantik açıklama yeterliyse iyi, değilse aynı hata döner. Rapor bunu açık soru olarak yazmış. Öneri: ilk onaylı chat testinde "I can't pay today" vakası; tekrar ederse `offer_asked` benzeri deterministik bir koruma (spec'ten bağımsız: en az bir `offer_message`/karşı öneri sorulmadan `close_values` kapanışa gitmesin). Bugün için kabul.

### 4. [Bilgi] `{{today_text}}` extraction açıklamasında çözülmeyebilir
- `offer_date` açıklaması "Today is {{today_text}}" içeriyor. Kit `{{var}}` yerleştirmeyi prompt, `on_enter.text`, geçiş açıklamaları, URL, header, gövde için sayıyor (`workflow-format.md:190`); extraction açıklaması listede yok. Çalışma zamanında literal kalabilir. Zararsız (çözücü kod tarafında `now` ile çalışıyor), ama tarihe güvenen bir açıklama sayılmasın; ya sil ya da yalnızca "copy the phrase unchanged" bırak.

## İstenen kontroller

| Kontrol | Sonuç |
|---|---|
| Düz anahtar ürün okuyucu gözlenen biçimle uyumlu mu | **Hayır** (bulgu 1). Önek `get_account_response`, gözlenen `account_response`. |
| Tarih çözücü `now`'a göre | `today()` spec'in `today_variable`'ından (fixture'larda `now`), yoksa sistem tarihi. Çözüm kod tarafında; el hesabı tablosu bulgu 2. |
| Tatil kaydırma | Doğru (10-26 → 10-27; Cumartesi → 10-19). |
| Tutar türleri | `full` → `max_amount` kuralı (`high`), `minimum` → `min_amount` kuralı (`low`); sayısal tutar önce geliyor; `other` ve sayı yok → `missing`; ürün başına kaynak farkı (kart / kredi) test edilmiş. `half` / `all but` gibi ifadeler yok, `other` olarak `missing`'e düşer (güvenli). Geçişte `offer_amount_kind` full/minimum ise `check_offer`'a gidiliyor. |
| Dürüstlük kuralı | Sistem prompt'una `create_promise` ok olmadan kayıt iddiası yok; not/geri arama için aynı; `negotiate` non-ok verdict'te `offer_message` önce; özel yolda cümle yalnızca tool `ok true` ise söyleniyor. İyi ve genel. `promise_progress` hook'u `create_promise_response.data.ok` yedeğini de okuyor. |
| Refusal tanımı | Bulgu 3: açıklama düzgün, deterministik koruma yok. |
| `close_call_ok` koruması | `closing_say → end_call` (ilk) ve `close_attempt` (always): hedefler farklı, sıra doğru (üretilen düğümde doğruladım). `close_call_ok` yalnızca `close_attempt` içinde sıfırlanıyor; hang-up hook'u zaten aynı değişkene bakıyor. Not: sohbet kapanıştan sonra yeniden açılırsa `closing` kodu ve tts yine çalışır (kapanış cümlesi tekrar söylenebilir), ama ikinci `close_call` gitmez; kabul. |
| Hardcode | Yok. Hafta günü ve ay adları İngilizce çerçeve sözcükleri (brief değeri değil); tatil, kural, sayı kodda yok. Sızıntı testi geçiyor. Prompt: A 598, B 564 token, hepsi 1.500 altında. |

## Kurallara uyum
Freya isteği yok, testler çevrimdışı, stdlib. Rapor F-032 (7 test beklentisi ve PROMPTS yenileme) kayıt altında.

## Düzeltme sonrası kontrol
Bulgu 1 ve 2 kapatılınca küçük bir yeniden bakış yeterli. Chat retest'te bakılacaklar: `products_facts` dolu mu (özellikle gözlenen `account_response.*` ile), "I can pay the full amount today" kabul, "Friday next week", "I can't pay today" ret sayılmıyor, yeniden açılan sohbette ikinci `close_call` yok.

---

# Fix kontrolü (bulgu 1, 2, 4; rapor: tasks/T-005e-report.md "Fix")

Kod değiştirmedim, Freya yok. `python3 -m unittest`: 104 test geçiyor. Üretilen `offer_setup` ve `check_offer` kodunu A ve B fixture'larından kendim `exec` ettim.

## Bulgu 1: kapandı
Ürün okuyucu artık sabit önek aramıyor, `<ad>_response.data.<products_field>.<i>.<alan>` kalıbını okuyor. Denedim (A ve B, 1 ve 2 ürün): `account_response.*` (gözlenen), `get_account_response.*` ve uydurma `foo_response.*` üçü de ürünleri buldu; `products_facts` ürün sayısı kadar `Product N:` satırı içeriyor ve dahili id (`p-card`) metinde yok. Ürün numarası hook'u ve özel yol ilerlemesi aynı üretilen okuyucuyu kullanıyor (diff). Testler hem gözlenen hem eski biçimi bir, iki, üç ürünle kapsıyor.

## Bulgu 2: kapandı
Bugün Çarşamba 2026-10-14 varsayımıyla, el hesabım ve çözücü çıktısı:

| İfade | Çözücü | El hesabı | Sonuç |
|---|---|---|---|
| today / tomorrow | 10-14 / 10-15 | aynı | doğru |
| the day after tomorrow | 10-16 | 10-16 | doğru (yeni) |
| this Friday / Friday | 10-16 | 10-16 | doğru |
| **Friday next week** | 10-23 | 10-23 | **düzeldi** |
| **next week Friday** | 10-23 | 10-23 | **düzeldi** |
| Monday next week / next Monday | 10-19 | 10-19 | doğru |
| next week (gün yok) | `missing` | belirsiz | güvenli |
| **next Friday** | `date_ambiguous`, mesaj "Do you mean Friday 16 October?" | belirsiz | **kabul edilmiyor, onay soruluyor** |
| Monday the week after next / Monday the 26th / the 26th | 10-26 tatil → öneri 10-27 | aynı | doğru |
| **the 20th** / on the 30th | 10-20 / 10-30 | 10-20 / 10-30 | doğru (yeni) |
| the 10th (geçmiş) | sonraki ay 11-10 → `date_too_late` | 11-10 | doğru |
| **Oct 20** / oct 20th / 20 October / October 20 | 10-20 | 10-20 | doğru |
| 2026-10-20 | 10-20 | 10-20 | doğru |
| Saturday | öneri Pazartesi 10-19 | aynı | doğru |
| 10/20, in two days | `missing` | — | güvenli |

- `date_ambiguous` teklifi kabul etmiyor ve ret sayılmıyor: aynı ifadeyle 5 kez denedim, `offer_rejections` 0 kaldı, `offer_limit` kapanışı tetiklenmedi.
- Küçük not (bilgi): bugünle aynı gün adı yalnız söylenirse ("Wednesday", Çarşambaysa bugün) çözücü bir sonraki haftayı (10-21) seçiyor; makul. `10/20` ve "in two days" `missing` (agent tekrar soruyor), kabul.

## Bulgu 4: kapandı
`offer_date` açıklaması artık `{{today_text}}` içermiyor; çözüm yalnızca kodda `now` ile. Bulgu 3 (deterministik refusal sayacı) talimata uygun olarak ertelenmiş, chat retest maddesi olarak kalıyor.

## Hardcode
Yeni kod yalnızca İngilizce hafta günü/ay adı çerçeve sözcükleri ve takvim hesabı içeriyor; brief değeri (tatil, sayı, sonuç adı) yok. Sızıntı testi geçiyor, prompt bütçesi altında.

## Karar: merge edilebilir
Bulgu 1, 2, 4 kapandı; yeni hata görmedim. Chat retest'te hâlâ bakılacaklar: gerçek Freya'da `account_response.*` ile `products_facts` dolu mu, "next Friday" onay sorusu akışı ("yes" tek başına tarihi kaybettirmiyor mu), "I can't pay today" ret sayılmıyor mu (bulgu 3), yeniden açılan sohbette ikinci `close_call` yok.
