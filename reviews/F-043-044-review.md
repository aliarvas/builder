# F-043 / F-044 review (bekleme cümlesi, insan dostu geri okuma)

Rapor: tasks/F-043-044-report.md; bulgular docs/UAT-FINDINGS.md F-043, F-044. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 223 test geçiyor. Üretilen workflow'u ve `offer_setup`/`check_offer` kodunu kendim çalıştırdım.

## Karar: merge edilebilir
F-043 kit kurallarına uygun ve passthrough'u bozmuyor. F-044 biçimleri doğru (ürün adı, konuşma dilinde tarih, ondalıksız tutar). Brief değeri yok. İki orta/düşük zayıflık (ürün adı çakışması, sabit "ending") ve bir doğrulama boşluğu (`wait_line`) var; hiçbiri engelleyici değil, ama çakışma çok ürünlü final brief'te geri okumayı belirsiz yapabilir (bulgu 1), final koşudan önce düzeltilmeli.

## F-043: bekleme cümlesi
- **Kit uyumu:** `workflow-format.md:468`: "Set `on_enter` to `{"type": "silent"}`, or to a short fixed line that covers the wait", ve `:160` `tts` sabit satır, model çağrısı yok. Üretilen `account` düğümü (kendim yazdırdım): `node_type: api_request`, `on_enter: {"type": "tts", "text": "Thank you. One moment while I check your account."}`, `passthrough: true`, `passthrough_default_transition: "offer_setup"`, geçişler: hesap hatasında `closing`, son geçiş `always → offer_setup`. Yani passthrough kuralları (varsayılan geçiş, `always` ile biten geçişler) bozulmamış. `offer_setup` ve `check_offer` hâlâ `silent`; müşteri art arda iki sabit cümle duymuyor.
- **Kaynak:** spec'te `agent.wait_line` varsa o (kırpılarak), yoksa `prompts.py` kataloğundaki `ACCOUNT_WAIT_LINE`. Cümle değişken içermiyor, borç ayrıntısı içermiyor ve doğrulamadan sonraki adımda söyleniyor (kimlik doğrulanmadan hesap adımına geçilmez), yani doğrulama öncesi yasaklı sözcük/ifşa riski yok.
- **Bulgu 3 (düşük): `wait_line` doğrulaması yalnızca "string".** `spec.py` `_string(..., empty=True)`; extraction tarafında (`extract.py`) alan için ayrıca kontrol yok. Söylenen sabit satırda çözülmemiş `{{değişken}}` aynen sesli okunur (kit `workflow-format.md:201`), bu yüzden `{{` içeren ya da çok uzun (ör. > 200 karakter) bir `wait_line` reddedilmeli (onarım). Ayrıca dil: alan yoksa varsayılan satır İngilizce; çağrı dili farklıysa (yalnızca `agent.language` İngilizce değilse) yanlış dilde söylenir. Final brief'ler aynı türde (İngilizce bekleniyor), bu yüzden düşük; en azından `agent.language` İngilizce değilken ve `wait_line` boşken `silent` kullanmak güvenli olurdu.
- **Kapsam notu:** platformun Türkçe dolgu cümlesinin bu satırla kaybolup kaybolmadığı yalnızca canlı chat'te görülür (rapor da böyle diyor, TO-CONFIRM).

## F-044: geri okuma
Kendi çalıştırmam (Brief B fixture, bugün 2026-10-14):
- **Tek ürün + etiket:** `credit card ending 0377` (tür `credit_card` → `credit card`; etiket `card_last4`'tan). Etiketi olmayan ürün: `personal loan`. Spec alanları yoksa sıra sözcüğü (`the first product`, tek üründe `the product`).
- **Özet:** `personal loan: 150 on Tuesday, 20 October [product number 1]`. ISO tarih ve "Product 1" yok; yıl yalnızca bu yıl değilse söyleniyor ("Monday, 4 January 2027", testli); tutar 420.00 → `420`, 95.5 → `95.50`; ürün numarası köşeli parantezde, onay şablonu "never say it to the customer" diyor.
- **Ürün bilgileri:** her satırın sonuna "Name it to the customer as: …" ekleniyor, iç id görünmüyor; mevcut `Product N` sayımı korunmuş (mevcut testler buna dayanıyor).
- **Genellik:** "ending", sıra sözcükleri ve ay/gün adları dile bağlı genel şablon parçaları; ürün türü ve etiket tamamen spec alanlarından geliyor; brief değeri yok.

### Bulgular
1. **[Orta] Aynı türde, etiketsiz iki ürün aynı adı alıyor.** Denedim: iki kişisel kredi (etiket alanı yok) → bilgi satırlarında ikisi için de `Name it to the customer as: personal loan` ve geri okuma `personal loan: 150 on Tuesday, 20 October [product number 1]; personal loan: 100 on Wednesday, 21 October [product number 2]`. Müşteri hangisinin hangisi olduğunu ayıramaz; önceden "Product 1/2" en azından ayırt ediyordu. Herkese açık test setinde böyle çakışma yok (kart + kişisel + araç kredisi, hepsi farklı), ama final brief'lerde üç ürünlü müşteri aynı türden iki ürün taşıyabilir. **Düzeltme:** adlar çakışıyorsa (aynı tür+etiket) çakışan ürünlere sıra sözcüğü ekle: `the first personal loan`, `the second personal loan`; ürünlerin yalnızca biri çakışıyorsa yalnızca çakışanlar.
2. **[Düşük] "ending" etiket değeri rakam olmasa da kullanılıyor.** `product_name` etiket doluysa her zaman `<tür> ending <değer>` diyor. Etiket alanı son haneler dışında bir şeyse (ör. takma ad) "credit card ending Savings" olur. Extraction prompt'u etiketi "such as its last digits" diye tanımlıyor, yani normalde rakam; yine de değer rakam dizisi değilse `ending` olmadan `<tür> <değer>` demek güvenli. Düşük.
3. **[Düşük] Tutar para birimi söylemiyor.** `420` (para birimi yok). Brief A'nın örneği de yalnızca sayıyla; para birimi spec'te yok, kabul.

## Spec ve extraction doğrulaması
- `spec.py`: `agent.wait_line`, `account.product_kind_field`, `account.product_label_field` isteğe bağlı, string; string olmayan değer `SpecError` (testli). Eski spec'ler değişmeden geçerli.
- `extract.py`: `product_kind_field`/`product_label_field` hesap aracının ürün alanlarından biri (ya da `""`) olmalı, değilse hata ve onarım (testli, ürün alanı olmayan değer reddediliyor). `wait_line` için ek kontrol yok (bulgu 3). Extraction prompt'u üç alanı genel dille tanımlıyor ("one short sentence in the language of the call ... no debt details"; "product item field with the kind of product, or \"\""; "such as its last digits").

## Brief değeri
Yeni/değişen prompt ve şablon metinlerini üç brief'ten çıkardığım jetonlarla taradım: ortak snake_case kod yok; "credit", "loan", "card", "4821", "Freya" extraction/onay/müzakere prompt metinlerinde geçmiyor. Sızıntı testi yeşil. Fixture'lardaki alan adları (`card_last4`, `type`) test verisi, builder koduna girmemiş.

## Kurallara uyum
Freya/model isteği yok, stdlib; `build.py`, `run_trace.py`, `submission_check.py` bu görevde değişmemiş.

## Canlı doğrulama için
PUB-01 chat'inde (rapordaki maddeler doğru): doğrulamadan sonra Türkçe dolgu yerine "Thank you. One moment while I check your account." duyuluyor mu; geri okuma "credit card ending …, 420 on Wednesday, 14 October" biçiminde mi, "Product 1" söylenmiyor mu. Çok ürünlü vakada (PUB-11) üç ürünün adları birbirinden ayrışıyor mu.
