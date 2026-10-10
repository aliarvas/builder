# F-052 review (F-051 review takibi, `none` ile enum sıfırlama)

Rapor: tasks/F-052-report.md; kaynak reviews/F-051-review.md bulgu 1–3 ve "açık risk". Kod düzenlemedim, Freya ve modele istek atmadım. `python3 -m unittest`: 263 test geçiyor. Bilgi: PUB-07 sürüm 13 (657e6a6) ledger'dan geçti; bu review F-051'in üstündeki F-052 değişikliklerini (çalışma ağacı) kapsar. Simülasyonları Brief B fixture'ı ve canlı Brief A spec'iyle (`traces/brief-a.spec.json`) üretilmiş kodu çalıştırarak yaptım (bugün 2026-10-14).

## Karar: merge edilebilir
Üç bulgunun üçü ve açık risk doğru kapatılmış; simülasyonlarım raporla birebir uyuşuyor. Küçük bilgi notları aşağıda; hiçbiri engelleyici değil.

## Bulgu 1: önerilen tutar türü ürün başına — kapandı
Brief B fixture'ı (kart + kredi): ürün 1'e taban altı teklif (`amount_too_low`, `proposed = minimum`), sonra yalnız tarih → taban 28,50 kabul → `proposed` **`full`'a döndü**; ürün 2'de yalnız tarih → kabul **300** (kredinin tam tutarı), önceki 150 hatası yok. Extraction açıklaması da "başka ürüne geçince, ajan o ürünün tabanını önermediyse `full`" diyor.

## Bulgu 2: tarihsiz kabul — kapandı
- Yeni `offer_accepts_proposal` (`yes | none`), yönlendirme koşulu "tarih dolu **veya** `offer_accepts_proposal = yes`" (üretilen geçişte doğruladım).
- PUB-07 akışı: "Monday the 26th" → `date_not_business_day`, öneri 2026-10-27; müşteri yalnızca "yes" → `check_offer` önerilen tarihi kullanıyor → **`ok`, kabul: `p1`, 2026-10-27, 540.0**, `offer_accepts_proposal` kontrolden sonra `none`. Önerilmiş tarih yokken yalnız "yes" → `missing` ("The date was not clear. Ask the customer for the exact date."), yani yanlış tarih uydurmuyor.
- `offer_date` açıklaması da "ajanın az önce önerdiği tarihi adını söylemeden kabul ederse tarihi ajanın söylediği gibi yaz" diyor; bu, ajanın kendi önerdiği (kodun üretmediği) tarihler için çıkarıcıya dayanıyor (canlı doğrulanacak).

## Bulgu 3: `missing` yalnızca tarih — kapandı
- `missing`: "The date was not clear. Ask the customer for the exact date."
- Yeni `amount_missing` ("başka bir tutar" deyip sayı vermedi): "The amount was not clear. Propose the amount again yourself: the full amount due, or the minimum if you offered it." — müşteriye "ne kadar ödeyebilirsiniz" sorulmuyor; **geçersiz teklif sayacına girmiyor** (`offer_rejections_by_product` boş kaldı). Doğrulandı.
- Bonus: `ok` mesajı "the credit card ending 0377 / the personal loan" gibi müşteriye görünen adı söylüyor ("product 1" yok); `product_unknown` "by its number" demiyor (F-044 ile uyumlu).

## Açık risk: enum değişkenleri `none` ile sıfırlanıyor — kapandı
- `FRAMEWORK_NONE_VALUE = "none"`. Üretilen workflow'larda extraction enum'larında `none` var: açılışta `caller_role` (`…, greeting, none`), `third_party_reply`, `negotiation_reply`, `readback_reply`, `offer_amount_kind`, `offer_accepts_proposal`; `offer_proposed_kind` yalnız `full`/`minimum` yazılıyor (`none` yok, gerek de yok).
- `opening_unclear` adımı `caller_role`'ü `'none'` yapıyor; `check_offer` kontrol sonrası `multi_product_intent` ve `readback_intent`'i `'none'` yapıyor (kendim çalıştırdım). Hiçbir geçiş literal `none` ile tetiklenmiyor (tüm geçişleri taradım: sıfır). `spec.py` `none`'ı kullanıcı değer listelerinde reddediyor, extraction route değerlerinde reddedip onarıma gönderiyor (testli). Çok ürünlü akışta `more` sonrası eski niyet `none` olduğu için ikinci ürün konuşulmadan onaya geçiş olmuyor. Özel yol sonuç değişkenleri enum olmadığı için `''` ile kalıyor (doğru).

## Bilgi notları
- Yalnız "yes" ile kabul, kodun önerdiği tarihe dayanıyor; ajan tarihi kendi cümlesiyle (ör. persuasion 1'in "haftanın son iş günü" önerisi) verirse kabul tarihi çıkarıcının ürettiği ifadeye bağlı. İlk canlı Brief A koşusunda persuasion sonrası "yes" vakası denensin.
- "Can you make this payment today?" sorusuna tarihsiz "yes" artık `missing` ile tarihi sordurur; makul (bugünü varsaymıyor).
- UAT'ta F-051/F-052 durumu güncellenmemiş olabilir; önerilen durum "fixed offline, retest pending" (PUB-07 v13 F-051'i canlıda doğruladı, F-052 değişiklikleri henüz canlıda denenmedi).

## Kurallar
Brief değeri yok (`none`, `yes`, `full`, `minimum` genel çerçeve sözcükleri); stdlib; Freya/model isteği yok.

## Canlı doğrulama için
Raporun listesi doğru: PUB-07'de önerilen tarihe yalnız "yes"; "rejected by schema validation" uyarısı olmaması; Brief B'de ikinci ürünün tam tutardan başlaması; açılışta belirsiz cevap sonrası `caller_role` `none` ve yeniden sorma.
