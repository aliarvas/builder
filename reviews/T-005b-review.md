# T-005b review (global özel yollar, deterministik çıkışlar, kodla teklif kontrolü)

**Reviewer:** claude-reviewer · **Kapsam:** `tasks/T-005b-globals-and-offer-check.md`, `tasks/T-005b-report.md`; `builder/offer_check.py` (yeni), `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`, `tests/test_multi_step.py`, `tests/fixtures/spec-*.json`.
**Karar: merge edilebilir.** Teklif hesabı bağımsız el modelimle 560 vakada sıfır sapmayla eşleşti, global node yapısı ve `excluded_nodes` doğru, `create_promise` değerleri kontrol edilmiş tekliflerden geliyor, kodda brief değeri yok. Üç bulgu (1, 2, 3) Brief B / çok ürün chat testlerinden **önce** ve gizli brief build'inden önce kapatılmalı; hiçbiri T-005b'nin yeni bir gerilemesi değil, ama ikisi (1 ve 2) skoru doğrudan etkiliyor. 75 test geçiyor, Freya'ya istek atılmadı, kod değiştirmedim.

## Yöntem

- Çevrimdışı çalıştırdım: `offer_setup_code` / `check_offer_code` / `_closing_code` çıktılarını `exec` ile `vars` sözlüğüyle koştum.
- **Bağımsız el modeli:** Brief A metninden (kural 18–23, 25–27) ve tatil listesinden kendim yazdım (fixture kurallarını kopyalamadan): iş günü = Pzt–Cum hariç 5 tatil; erken bant 12., geç bant 7. iş günü; geçerli tarih: bugün veya sonrası, iş günü, son tarihten sonra değil; tatil/hafta sonu ≤ son tarih → sonraki iş günü; son tarihten sonra → son tarih; tutar: taban (kart `minimum_payment`, kredi `instalment_amount`) ile borç arası dahil. Bugün 2026-10-14 (Çarşamba), 4 ürün (erken kart, geç kredi, 7 gün kredi, 8 gün kart), 20 tarih gününden fazla × 4 tutar = **560 vaka: 0 sapma** (verdict ve önerilen tarih). Ayrıca bugün = 10-14, 16, 22, 23, 24, 25, 26, 27, 11-10, 11-11, 12-24 için 1.056 tarih vakası: tüm fark yalnızca etiket (bugün hafta sonu/tatilken bugünle sonraki iş günü arasındaki tarihler `date_not_business_day` yerine `date_too_early` çıkıyor; önerilen tarih aynı). Yani tatil kayması, bant son tarihi (11-02 ve 10-23, tatil 10-26 atlanarak), hafta sonu → pazartesi, tatil → 10-27, geçmiş tarih → bugün, taban/borç sınırları doğru.

## İstenen kontroller

### 1. Global node `excluded_nodes` doğru mu?

- **Doğru.** A: `special_already_paid` ve `special_dispute` yalnızca `negotiate` ve `confirm_record`'dan tetiklenebilir (excluded 35 düğüm); `special_human` `identity`, `negotiate`, `confirm_record` (spec'in `available_in`'i). Kimlik öncesi hesap konuşması riski yok: `opening`/`third_party`/`account` hariç; `identity` yalnızca `human` için açık (A kural 42: "before and after verification").
- Kapanış zinciri (`closing`, `closing_say`, `close_attempt`, `close_record`, `end_call` ve tüm `close_*`), `offer_setup`, `check_offer`, `confirmation_progress`, `*_go` düğümleri ve diğer global node'lar da hariç, yani kapanış döngüsü veya global-içinde-global döngüsü oluşamaz. Hariç listesi son adımda, `nodes` tamamlandıktan sonra hesaplanıyor (hiçbir düğüm atlanmıyor).
- `then: return` → `__previous__`; `then: close` → `close_special_<id>` durum düğümü (yalnızca bu güne kadar `closing` zincirine gidiyor). Başarısız araç → `close_special_tool_failed` (isteğe bağlı durum, spec eşlemezse `default` satırı).
- Normal adımlarda kopya (`special_<id>_from_*`) yok.
- **Doğrulanmamış (TO-CONFIRM):** global node'un yalnızca deterministik geçişi olan bir adımdan gerçekten tetiklenmesi; passthrough ve `api_request` tipinde global node'un çalışması (kit örneği yalnızca tts + sohbet tipi gösteriyor); `__previous__`'ın doğru adıma dönmesi.

### 2. Özel yol çıkışlarında `matches_intent` kaldı mı?

- **Kalmadı.** Render edilen A workflow'unda `matches_intent` yalnızca üç global node'un `condition`'ında (olması gereken yer); hiçbir adım geçişinde ve hiçbir özel yol çıkışında yok, `is_tool_call` hiç yok. Çıkışlar: araçsız → `always`; engine aracı → `data.ok` true/True'ya göre; model-doldurmalı araç → araç `response_mapping` sonucu (`special_result_<id>`); `ask` varsa `proceed/stay` enum'u.

### 3. `check_offer` kural formatı genel mi, hesaplar doğru mu?

- **Genel.** Format spec verisi: `non_business_weekdays` (ISO gün numaraları), `holidays` (ISO tarihler), `earliest`/`latest` (gün sayısı + `business|calendar`), `when` koşulları (`min`/`max`/`equals`/`in` ürün alanları üzerinde, ilk eşleşen kazanır), `latest_on_non_business_day` (`previous|next|keep`), `min_amount`/`max_amount` (alan, sabit değer veya `share` oranı), `max_rejected_offers`. Kodda alan adı, tarih veya sayı yok; synthetic fixture bilerek farklı kurallar kullanıyor (yalnızca Pazar tatil, en erken 1 iş günü, 20 takvim günü + `next` kayması, taban = borcun yarısı, ret sınırı 2). Spec doğrulaması hatalı biçimleri (ISO olmayan tatil, bilinmeyen birim, `field`+`value` birlikte, sıfır sınır) açık hatayla reddediyor.
- **Doğruluk:** yukarıdaki 560 + 1.056 vaka; ayrıca sınır tutarlar (taban − 1, taban, borç, borç + 1) doğru. Brief B kuralları aynı fixture formatıyla ürün başına hesaplanıyor (ürün alanından bant/taban).
- Kontrol sırası makul: ürün belirsiz → eksik → erken → geç → iş günü değil → düşük tutar → yüksek tutar. Brief A kural 20/23 sırası doğru (son tarihten sonra gelen tatil `date_too_late` → son tarih; kural 20 yalnızca ≤ son tarih için).

### 4. `create_promise` değerleri kontrol edilmiş değişkenlerden mi?

- **Evet.** Şemadan tarih ve tutar alanları kaldırıldı; model yalnızca ürün numarasını veriyor. `promise_values_hook` (pre-hook) `offers_accepted` sözlüğünden (`check_offer`'ın `ok` verdict'inde yazdığı, ürün numarası → id/tarih/tutar) id, tarih ve tutarı gövdeye yazıyor. Model yanlış numara verirse (birden çok kabul varken) hook gövdeyi değiştirmiyor ve API reddediyor (dürüst başarısızlık); tek kabul varken tek girişe düşüyor. Geri okuma `offers_summary` (`{{offers_summary}}`) üzerinden "birebir" yapılıyor.

### 5. Kodda brief değeri var mı?

- **Yok.** Alt dize taraması (banka adı, tarih/tutar, outcome/reason adı, kuyruk adı, saat penceresi, `minimum_payment`, `instalment`, `date_of_birth`, `phone_last4`, `mobile app`, `branch`): `builder/*.py` temiz. `holiday`, `deadline`, `business day` yalnızca genel iş sözcüğü olarak (`offer_check.py`, `prompts.py`, `spec.py`). Doğrulama verdict cümleleri (`OFFER_VERDICT_MESSAGES`) genel.
- Bkz. bulgu 2 (OpenAPI alan adı `field` kodda) ve 6 (sızıntı testi gevşetmesi).

## Bulgular (önem sırasıyla)

### 1. [Orta-Yüksek, Brief B öncesi] Beklenen ürün sayısı varsayılanı 1: çok ürünlü akış erken `ready` olabiliyor
- `offer_check.py` `CHECK_BODY`: `expected = int(vars.get(expected_variable) or 1)`, `expected = max(1, min(expected, len(products)))`; `progress = 'ready' if len(accepted) >= expected`. `confirmation_progress` aynı değere dayanıyor (`OFFERS_ACCEPTED_COUNT or expected_variable or 1`). `expected_variable` negotiate extraction'ından (integer, `min_confidence 0.8`) geliyor; extractor boş bırakırsa varsayılan 1.
- Brief B: "ürünleri sırayla geç, her biri için söz veya not; hepsini birlikte geri oku; bir kez onay; ürün başına `create_promise`". Müşteri üç ürünü de kabul ederken extractor sayı vermezse ilk geçerli teklif `ready` yapar, `confirm_record`'a gidilir ve 2. ve 3. ürün hiç sorulmaz (ledger'da eksik söz). Ayrıca bir ürün reddedilir/itiraz edilirse ve not yazılırsa "bitti" koşulu hiç oluşmaz.
- **Düzeltme (genel):** varsayılanı `len(products)` yap ve "tamamlanma"yı ürün başına duruma bağla: her ürün `accepted` veya `noted` (ret/itiraz/ödendi/hata) olunca `ready`. Müşteri "bu kadar" derse (`negotiation` kapanış niyeti) mevcut kabullerle `confirm_record`'a gidilsin (bu geçiş zaten var). `expected_count` extraction'ı kaldırılabilir/yedek olur.

### 2. [Orta, gizli brief build riski] OpenAPI alan adı `field` kodda sabit: kimlik doğrulama enum'u
- `builder/workflow.py:516-527`: `identity_body.get("properties", {}).get("field", {})` ve `.get("enum", [])`. Gizli tool dosyasında `verify_identity` soru seçici alanı başka adlıysa (ör. `question`), `field_schema = {}` → `allowed_identity_fields = []` → tüm kimlik soruları "bilinmeyen" sayılıp `SpecError` ile build **çöker**. Kit: "In a final brief their fields and allowed values may change."
- Aynı örüntü başka yerde de aranmalı (tool alan adlarının koda yazılması). Bu, T-004'ten kalma; T-005b ile sızıntı testi gevşetildiği için (bulgu 6) test de yakalamıyor.
- **Düzeltme:** soru alanını sabit ada bağlama. `verify_identity` gövdesinde enum'u olan ve spec sorularının `field` değerlerini içeren özelliği ara; tek bir aday varsa doğrula, bulunamazsa doğrulamayı atla ve trace'e `warning:` yaz (build'i durdurma). Alternatif: spec'e `identity.selector_field` ekle.

### 3. [Orta, TO-CONFIRM] Eski `special_result_<id>` değeri: aynı yol ikinci kez tetiklenince araç çağrılmadan çıkabilir
- `workflow.py` `_special_nodes`: model-doldurmalı araçlı yol (B `add_note`, ürün numarası) çıkışını `special_result_<id> equals true/True` ile yapıyor; değişken yalnızca `check_offer` çalışınca sıfırlanıyor (`reset_variables`). Bir ürüne itiraz notu yazılır (`True`), müşteri aynı adımda başka bir ürüne de itiraz ederse (`check_offer` araya girmediyse) yol yeniden tetiklendiğinde değişken hâlâ `True`: ilk yönlendirmede araç çağrılmadan `__previous__`'a çıkılır ve ikinci ürün notu hiç yazılmaz. Brief B kural 8/9 (ürün başına not) ve çok itirazlı vakalar.
- **Düzeltme:** çıkış koşulunu çağrıya özgü hale getir. Seçenekler: aracın `pre_process_code`'u çağrı öncesi `special_result_<id>`'ı temizlesin ve çıkış yalnızca aracın `response_mapping` sonucuna dayansın; yol girişinde değişkenin dolu olması hâlinde çıkışın tetiklenmemesi için ayrıca bir `special_called_<id>` işareti kullanılabilir. Chat testinde Brief B'de iki itirazlı bir vaka (veya PUB-12/13 varyantı) bunu doğrular.

### 4. [Düşük] Tutar metni ayrıştırma: binlik ayırıcılı string yanlış okunuyor
- `offer_check.py` `parse_amount`: `'1,200'` → 1.2 (`amount_too_low`), `'1.200,50'` → 1.2005. Çıkarım tipi `float` olduğundan değer normalde sayı gelir, ama "iki parça halinde söylenen" tutarlar metin olarak gelirse hatalı red olur.
- **Düzeltme:** yalnızca virgül varsa ve son virgülden sonra tam 3 hane varsa binlik say; hem nokta hem virgül varsa sonuncusu ondalık olsun.

### 5. [Düşük] Bugün hafta sonu veya tatilken `date_too_early` etiketi
- Davranış doğru (önerilen tarih bir sonraki iş günü), yalnızca etiket farkı; mesaj "earliest allowed date" diyor. İşlem gerekmez, bilgi.

### 6. [Düşük] Sızıntı testi: OpenAPI alan adları da izinli sayılıyor
- Rapor: "OpenAPI'nin alan adları da değerleriyle birlikte sözleşme sayılıyor." Bu, kodda sabit yazılmış bir tool alan adını (bulgu 2'deki `field` gibi) gizler. Bugünkü kesişim: `date, error, field, ok, outcome, reason, text, type` kaynakta literal olarak geçiyor; çoğu genel anahtar (spec alan adları, Freya şeması), ama `field` gerçek bir API alan adı kullanımı.
- **Düzeltme:** alan adlarını izinli yapmak yerine "bu literal'ler kaynakta şu dosya/satırlarda izinli" biçiminde dar bir liste tut; `field` düzeltilince listeden düşsün.

### 7. [Bilgi, T-006'ya not]
- `max_rejected_offers` Brief A'da sayısal olarak yok (fixture 3); ikna denemeleri (kural 30) bu sayaçla aynı şey değil. Extractor brief'ten varsayılan seçerse bunu trace'e yazmalı.
- Rapor "kapsam dışı" olarak belirtiyor: A kural 30 ikna önerileri (haftanın son iş günü, taban ve son tarih) ve B kural 6 (tek tarih ürünün son tarihini aşarsa o ürün kendi son tarihine) otomatik uygulanmıyor, yalnızca öneri veriliyor; geri arama penceresi (A kural 6–7) hâlâ kodda değil.
- Prompt bütçesi (B): identity 479, negotiate 233, confirm_record 232, özel yollar 121–185; hepsi 1.500 altında.

## Doğrulananlar

- Global node'lar adım kopyalarının yerini aldı; sohbet adımı sayısı azaldı (A 12 → 8, B 10 → 7 — rapor).
- Hata kontrolü: bozuk/eksik girdide kod hata atmıyor; her çıktı değişkeni dolu (`vars` yedekleri); kodda `{{`/`}}` yok (JSON `{` kaçışıyla gömülü).
- `negotiate` çıkışı artık etikete bağlı değil: tarih ve tutar doluyken (ve `not_equals ""` koruması) `check_offer`'a gidiyor. Kabul sayacı yalnızca farklı teklifleri sayıyor (aynı eski teklifin tekrarı sayaç artırmıyor).
- Freya yok; testler çevrimdışı.

## Karar: merge edilebilir
Teklif kontrolü bağımsız el modelimle birebir eşleşiyor, özel yollar kopyasız ve deterministik çıkışlı. **Bulgu 1 ve 2** küçük/orta işler: 1 Brief B'nin çok ürünlü vakalarını, 2 gizli brief'te build'in çökme riskini kapatıyor; ikisi de bir sonraki görevde (T-005c) ilk sırada yapılmalı. Bulgu 3 chat testinde (iki itirazlı B vakası) doğrulanmalı. İlk onaylı chat testinde (PUB-01, PUB-07) ek olarak gözlenecekler: global node tetiklenmesi, `offer_date`'in ISO biçiminde gelmesi, "Yes" cevabından tutarın çıkarılması ve `create_promise` ledger değerleri.

---

# Fix kontrolü (T-005b-fix, rapor: tasks/T-005b-fix-report.md)

Kapsam: bulgu 1–6, yeni hardcode. Kod değiştirmedim, Freya'ya istek atmadım. `python3 -m unittest`: 81 test geçiyor. Yöntem: `git diff` okuması ve Brief B için üretilen `special_product_dispute_done` geçişlerinin dökümü.

## Bulgu durumu

| # | Bulgu | Durum |
|---|---|---|
| 1 | Beklenen ürün sayısı 1 varsayılanı | **Kapandı.** `ready` artık `len(handled_numbers(accepted)) >= len(products)` (`offer_check.py`). Kabul edilen veya not düşülen her ürün sayılıyor. `expected_variable` config'ten çıktı. Not: tüm ürünlere not düşülüp hiç kabul yoksa `ready` olmaz (`accepted` boşsa `open`); bu bilinçli, rapordaki açık soru 1. |
| 2 | OpenAPI `field` adı kodda sabit | **Kapandı.** `_check_identity_fields` spec'in tüm soru alanlarını kapsayan herhangi bir enum'u arıyor, bulamazsa build durmuyor, trace'e `warning` yazıyor. `workflow.py`'de `"field"` literal'i kalmadı (grep). |
| 3 | Eski `special_result_<id>` | **Yapı olarak kapandı, ama yeni bir hata var (aşağıda, Yeni-1).** Giriş kod adımı sonucu boşaltıyor, kaynak adımı kaydediyor, çıkış yalnızca o çağrının sonucuna bağlı. Doğru yaklaşım. |
| 4 | `parse_amount` binlik ayırıcı | **Kapandı.** `1,200`→1200, `1.200,50`→1200.5, `1,200.50`→1200.5, `12,50`→12.5, `1.200.000`→1200000. Tek noktalı `1.200` ondalık sayılıyor; belirsiz, kabul edilebilir. |
| 5 | Etiket farkı | **Kapandı.** `earliest_counted()` ile "gerçekten erken" ve "yalnızca iş günü değil" ayrılıyor. |
| 6 | Sızıntı testi alan adı izni | **Kapandı.** Toptan izin kalktı, dosya bazlı dar liste ve gerekçeler var; `field` için ayrı koruma testi eklenmiş. |

## Yeni bulgu

### Yeni-1. [Orta-Yüksek] `_done` adımında aynı hedefli geçişler birleşiyor, Brief B'de yönlendirme bozuluyor
- `workflow.py` `_model_tool_special` (`_done` geçişleri, yaklaşık satır 380–395). Brief B'de `available_in` = `negotiate`, `confirm_record`. Üretilen geçiş sırası: (1) `offer_progress equals ready` → `confirm_record`; (2) `from equals negotiate` → `negotiate`; (3) `always` → `confirm_record`.
- Kit `workflow-format.md:408`: aynı `target_node`'a giden geçişler yükleme sırasında tek geçişe birleşir, biri koşulsuzsa birleşen koşulsuz olur. (1) ve (3) aynı hedefte, yani birleşince koşulsuz `confirm_record` olur. Rapor bu riski görmüş ("son kaynak yalnızca always yedeğiyle hedefleniyor") ama (1) de aynı hedefe gidiyor, bu yüzden önlem yetmiyor.
- Sonuç, birleşik geçişin yerine göre: birinci sırada kalırsa `negotiate`'ta itiraz notundan sonra her zaman `confirm_record`'a gider (hiç kabul yokken söz kaydı adımına düşer); sonda kalırsa `ready` kısayolu kaybolur ve `negotiate` kaynağından hiç `confirm_record`'a geçilmez. İki durumda da amaçlanan davranış bozuk. Brief A'da yok (tek kaynaklı yol). Test "geçiş sırası"nı doğruluyor ama birleştirmeyi simüle etmiyor.
- **Düzeltme:** hiçbir hedef iki kez geçmesin. `confirm_record`'a giden tek geçiş `always` yedeği olsun; kaynak geçişleri koşula `offer_progress not_equals ready` ekleyerek dönsün: `from equals negotiate AND progress not_equals ready → negotiate`, son kaynak yedeği `always → confirm_record` (kaynak `confirm_record` ise ready için de aynı). Böylece (1) tamamen kalkar. Kaynakların hiçbiri `confirm_record` olmayan bir spec'te ayrı bir `ready → confirm_record` geçişi sorun değil; kural: aynı hedef için tek geçiş yaz. Genel çözüm olarak üretimde hedefe göre grupla, grup içinde koşulları OR'la, hiçbir hedefi iki kez yazma, sıralamayı engine'in birleştirmesine bırakma. Bir birim test: üretilen her node'da `target_node` tekrarının olmadığını kontrol etsin (tüm fixture'lar için).

### Yeni-2. [Düşük, bilgi] Araç adları kodda sabit
- `workflow.py:34,598,608,667`: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. Bunlar kitin sabit banka API'si (görev tanımı: hidden brief'te aynı tool dosyası); önceki turlarda kabul edilmişti. Gizli tool dosyası farklı adlar taşıyabilirse build `KeyError` ile çöker; en azından anlaşılır bir hata mesajı olsun.

## Hardcode kontrolü
Brief değeri (tatil, tarih, sayı, sonuç adı) yeni kodda yok. Yeni giriş/`_done` adımları spec'ten (`path.id`, `available_in`, `product_number_field`) üretiliyor. Prompt metni değişmemiş. Adım başına prompt: identity A ~506, B ~479 token, hepsi 1.500 altında.

## Kurallara uyum
Freya isteği yok, testler çevrimdışı, stdlib. TO-CONFIRM'ler (global **kod** node'u, `add_note_args.<alan>` düz anahtarı, B iki ürünlü akış) ilk onaylı chat testine kalıyor.

## Karar: düzeltme gerekli
Bulgu 1, 2, 4, 5, 6 kapandı; 3'ün yapısı doğru. **Yeni-1** (aynı hedefli geçişlerin birleşmesi) Brief B'nin ürün itirazı yolunu doğrudan bozduğu için chat testinden önce düzeltilmeli. Düzeltme küçük (geçiş listesini hedefe göre grupla); sonra hızlı bir yeniden bakışla merge edilebilir.

---

# Fix 2 kontrolü (Yeni-1, Yeni-2; rapor: tasks/T-005b-fix-report.md "Fix 2")

Kod değiştirmedim, Freya yok. `python3 -m unittest`: 93 test geçiyor. Yöntem: `git diff` okuması, A ve B fixture'ları üretip her node ve global node'da `target_node` tekrarı taraması.

## Yeni-1: kapandı
- `group_transitions_by_target` (`workflow.py` ~165): aynı hedefe giden deterministik geçişler OR ile tek geçişe birleşiyor, birleştirme sırası ilk görünen yere göre sabit. Koşulsuz veya niyet/araç geçişi başka bir geçişle çakışırsa build `internal:` hatasıyla duruyor (sessiz birleştirme yok). Doğru tasarım.
- Brief B `special_product_dispute_done` şimdi: (1) `from == negotiate AND offer_progress != ready → negotiate`, (2) `always → confirm_record`. Hedef tekrarı yok; `ready` ve diğer kaynak durumlarının hepsi yedeğe düşüyor. Önerdiğim çözümle aynı.
- Tarama: A ve B'de hiçbir node veya global node'da tekrar eden `target_node` yok. Raporun bulduğu üç ek yer (`negotiate`, `close_record`, B özel yol) de OR'lanmış tek geçişe dönmüş.
- Küçük not (Düşük): gruplayıcı çakışmada `ValueError` fırlatıyor; gizli brief'te bir spec bu duruma düşerse 30 dakikalık build çöker. Üretilen tüm node'ları yalnızca builder üretiyor ve fixture'lar temiz olduğu için olasılık düşük; yine de `build.py` bu hatayı `internal error` mesajıyla ve çıkış kodu ile yakalamalı (şu an yakalanıp yakalanmadığını doğrulamadım).

## Yeni-2: kapandı
- `_tool_index`: eksik araçlar, bulunan araçlar ve adın OpenAPI yolunun son parçasından alındığı açık mesajla `SpecError`. Araç adlarının sabit kalması kit gereği kabul.

## Hardcode
Yok. `Karar: merge edilebilir.`
