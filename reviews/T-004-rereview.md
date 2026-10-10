# T-004 re-review (fix turu)

**Reviewer:** claude-reviewer · **Kapsam:** `reviews/T-004-review.md` bulguları 1, 2, 3, 4, 6, 7, 8 ve 5(b)(c); 5(a)(d) T-005'e bırakıldı. `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`, `tests/test_multi_step.py`, `tests/fixtures/spec-*.json`.
**Karar: düzeltme gerekli (küçük).** Önceki bloklayıcıların yapısı doğru kurulmuş (çok ürün sayacı, tek yeniden deneme, `unclear` sayacı, `available_in/then`, sabit `3` kalktı), 48 test geçiyor. Ama çok ürünlü yolun doğruluğu iki doğrulanmamış motor davranışına bağlı ve biri aktif olarak yanlış sonuç üretebilir (bulgu N1); 500 hatasında sınırlı yeniden deneme ulaşılamıyor (N2). İkisi de küçük, genel düzeltmeler; Freya testinden önce yapılmalı, çünkü chat testi bunları ayırt edemeyebilir.

## Gözlemler

- `python3 -m unittest`: 48 test geçti. Freya'ya istek atılmadı, kod değiştirmedim.
- Fixture A/B/synthetic render edildi (çevrimdışı). Adım başına prompt tahmini (artık araç açıklamaları dahil): A 128–384, B 140–375, synthetic 98–232 token: üst sınırın çok altında, alt sınırın (500) hâlâ altında (fixture'lar iskelet; bkz. önceki review).
- Kaynak taraması (alt dize): `builder/*.py` içinde banka adı, tatil/tarih, outcome/reason adı, kuyruk adı, saat penceresi yok. `min(len(products), 3)` kalktı (`workflow.py:185` artık `0 <= index < len(products)`).

## Önceki bulguların doğrulanması

| # | Durum | Kanıt / not |
|---|---|---|
| 1 | **Kapandı, koşullu** (N1, N2, N3 görmezden gelinirse) | `workflow.py:466-489`: `confirm_record` → araç sonucu `promise_result_ok` dolunca `confirmation_progress` (kod düğümü) → `complete`/`exhausted` ise `closing`, değilse `confirm_record`'a dönüş. Sayaç mantığı `test_confirmation_progress_supports_multiple_products_and_one_retry` ile sınanmış (2 ürün: continue→complete; 1 ürün: retry→exhausted, `max_attempts_per_product` spec'ten). Açık riskler aşağıda. |
| 2 | **Kapandı** | `opening`'e `close_values` (→ `closing`) ve `stay_values` (→ `opening_unclear` kod düğümü: sayaç +1, ikinci seferde `closing`, aksi `opening`'e dön) eklenmiş (`workflow.py:361-380,406-413`). Fixture A: `unclear` yalnızca `stay_values`'ta, `third_party_values` yalnızca `third_party`. Not: eşik `greater_than 1` kodda sabit (N4). |
| 3 | **Kapandı** | `SpecialPath.available_in` (adım listesi, bilinmeyen adım hatası) ve `then ∈ {close, return}` (`spec.py:50-51,180-189`); her (yol, kaynak adım) için ayrı `special_<id>_from_<adım>` düğümü, `return` → kaynak adım, `close` → `closing` (`workflow.py:346-359,508-527`). Test: `test_special_availability_return_and_deterministic_transition_order`. Fixture B'de `product_dispute` `then=return`. Açık: `add_note` `product_id`'si modele serbest bırakılmış (N5). |
| 4 | **Kapandı** | Sabit `3` kalktı; `vars` için üç kaynak denenir (mapped değişken, JSON-string, `get_account_response.data.<products_field>`) (`workflow.py:163-192`); test 4 ürüne kadar eşler ve kötü girdide hata atmaz. Numara listesi hâlâ numaralı gösterilmiyor (T-005'e). |
| 5(b)(c) | **Kapandı** | `closing`: `close_call_failure_count > 1` → `end_call`; `max_turn_transition="end_call"` (`workflow.py:493-500`). Açık: başarı koşulu `ok` yerine sayaç (N3). |
| 6 | **Kapandı** | `confirm_record` → `negotiate` (revise) `confirm_record.transitions[0]` (`workflow.py:469-472`); `account` hatasında `account_failure_count > 0` → `closing`, `maxRetries = 1` (`:387`, `:447-452`). |
| 7 | **Kapandı** | Her adımda deterministik geçişler özel yollardan önce (`test_special_availability…`). |
| 8 | **Kapandı** | Anlamsız `is_tool_call` testi kaldırılmış/yerine yeni testler gelmiş; hook testi 4 ürün ve üç kaynak biçimini kapsıyor. Hardcode taraması hâlâ yalnızca tam eşleşme (alt dize/sayı taraması yapmıyor); önceki notum geçerli, düşük. |

## Yeni bulgular (önem sırasıyla)

### N1. [Yüksek] Model-doldurulan `product_number` alanı, hook'un yazdığı değişkenle çakışıyor → ikinci ürün birinciyle kaydedilebilir
- `workflow.py:180` (`vars[product_number_field] = choice` pre-hook içinde) ve `:205` (`default: "{{<number_field>}}"` aynı ad). `confirmation_progress` kodu da bu değişkeni okuyor (`:264`, test `variables = {…"selected_product_number": 1…}`).
- Kit kuralı (tools-and-code.md): "bir `{{var}}` default'u, düğüme girişte çözülür; modelin doldurduğu alan, giriş anında zaten set olan bir değişkenle aynı adı taşımamalı, yoksa değer **baked** olur ve model parametreyi hiç görmez". Akış: ürün 1 kaydedilir → hook `vars['selected_product_number'] = 1` yazar (kalıcıysa) → `confirmation_progress` → `confirm_record`'a **yeniden giriş** → alan artık `1` ile baked → 2. çağrı yine ürün 1'i kaydeder (veya ikinci ürün hiç seçilemez). Brief B çok ürünlü vakalar (3 vaka) bozulur. Pre-hook `vars` yazımının kalıcılığı belgelenmemiş (belgelenmiş olan post-hook'un yazması), ama kalıcıysa bu bug; kalıcı değilse sayaç anahtarı boş string olur (`promise_attempts_`) ve ürün başına deneme sayımı ürünler arasında karışır. İki durumda da bozuk.
- Test bunu yakalamıyor: `exec(code, {"vars": variables})` ile değişkenleri elle kuruyor, motorun baked davranışını modellemiyor.
- **Düzeltme (genel):** kalıcı değişkeni model alanından ayır ve motorun belgelenmiş çıktısını kullan: kit "model argümanları `<tool>_args.<field>` olarak saklanır" diyor (trial call'da görüldü). `confirmation_progress` ürün numarasını `vars.get('create_promise_args.' + number_field)` (düz anahtar) ile okusun; pre-hook `vars[...]` yazmasın. Yazması gerekirse farklı ad kullan (`last_<number_field>`), ama asla model alanıyla aynı ad değil. Test: `{{number_field}}` yer tutucusunun adının hiçbir kod düğümü/hook tarafından `vars`'a yazılmadığını doğrulayan bir statik test.

### N2. [Yüksek] `promise_result_ok is_set` ve `vars.pop` doğrulanmamış davranışlara dayanıyor; HTTP hatasında sayaç hiç çalışmıyor
- `workflow.py:215` (`response_mapping data.ok → promise_result_ok`), `:473-475` (`is_set` geçişi), `:281` (`vars.pop('promise_result_ok', None)`), `:407` (`vars.pop(who_answered)` aynı kalıp).
- (a) Kit "yazılan her anahtar workflow değişkeni olur" diyor; **silme** davranışı belgelenmemiş. `pop` değişkeni silmezse `promise_result_ok` dolu kalır: `confirm_record`'a her yeniden girişte `is_set` hemen yeniden tetiklenir, `confirmation_progress` aynı sonucu tekrar sayar (`recorded_count` şişer, `complete` yanlışlıkla gelir; ya da sonsuz ping-pong 30 turda kapanışa). `opening_unclear` için aynı: `who_answered` silinmezse bayat `unclear` her yönlendirmede sayacı artırır.
- (b) `create_promise` **500** döndürürse (OpenAPI: "service failed … may be repeated"; PUB-10 hata enjeksiyonu), T-003 post-hook zarfı yeniden yazar ama `data.ok` yok → `promise_result_ok` hiç set edilmez → `is_set` tetiklenmez → `confirmation_progress` hiç çalışmaz, `exhausted` yolu (ikinci başarısızlıkta kapanış) **ulaşılamaz**; model kendi yeniden denemesini 30 tur sınırına kadar sürdürebilir. Yeniden denemenin başarıya ulaştığı tek-hata senaryosu (PUB-10) modelin kendi çağrısıyla yürür ama sayaç/`service_error` yolu çalışmaz.
- **Düzeltme:** (1) Silme yerine sentinel yaz: `vars['promise_result_ok'] = 'consumed'` ve geçişi `equals true/True/false/False` (dört operand, `is_set` değil) yap; böylece tüketim `pop` davranışına bağlı olmaz. (2) Genel post-hook (`tools_from_openapi.py`, T-003-fix alanı) HTTP hatasında ve `ok` yoksa `data['ok'] = False` yazsın; bu normalize edilmiş `ok` hem `response_mapping`'te hem sayaçta kullanılır. (3) `opening_unclear` için de `pop` yerine `vars[who_answered] = ''`/sentinel. (4) Chat testinde (onaylı) tek adım: ilk çağrı başarısız (500), ikincisi başarılı → `recorded_count == 1`.

### N3. [Orta] `closing` başarıyı HTTP sayacıyla belirliyor, `ok` ile değil (T-001'den gerileme)
- `workflow.py:493-498`: `close_call_success_count > 0` → `end_call`. T-001 `close_call_response.data.ok` ("true"/"True") kullanıyordu. Banka `ok:false`'u HTTP 200 ile döndürüyor ("`ok` is false when the action was not carried out"); sayaç HTTP düzeyinde ise geçersiz outcome/reason (yanlış enum çifti) kapanışı "başarılı" sayar ve çağrı kayıtsız biter (F-012'ye benzer, dürüstlük). Aynı sorun `schedule_callback` ve özel araç çıkışlarında daha az kritik (her iki sayaç da çıkış).
- **Düzeltme:** `closing` geçişini `close_call_response.data.ok` `equals true/True` ile yap; başarısızlıkta yalnızca `ok == false/False` veya `failure_count > 1` ile çık (bkz. N2 (2): normalize `ok`).

### N4. [Orta] Yeni sabit: "iki kez belirsiz" eşiği kodda
- `workflow.py:410`: `greater_than 1`. Bu Brief A kural 3'ün sayısı ("bir kez daha sor, hâlâ belirsizse kapat"); gizli brief'te 3 deneme olabilir. AGENTS.md öncelik 1 (brief değeri koda girmez).
- **Düzeltme:** `opening.max_unclear_asks` (spec alanı, doğrulamalı pozitif tamsayı) ve `greater_than (max_unclear_asks - 1)`. Aynı şekilde `max_attempts_per_product` zaten spec'ten (iyi).

### N5. [Orta] `add_note` için `product_id` yine modelin serbest metni (F-008 tekrarı)
- Fixture B `special_product_dispute_from_*`: `add_note.body.product_id` `default: "{{product_id}}"`, `required: ["product_id"]`; ürün numarası/hook yok. `product_id`'yi modelin yazması F-008'deki "uydurma id" hatasını `add_note` yolunda yeniden açar (Brief B kural 8/9/11).
- **Düzeltme:** hook mekanizmasını genelleştir: `product_id` alanı olan **her** araç (alan adı spec'te `account.product_id_field`) için aynı "numara → id" dönüştürmesi (`_promise_tool`'un `add_note`/diğer araçlar için de uygulanması). Not: `service_error` notu (Brief B kural 11) için `confirm_record`/`exhausted` yolunda `add_note` hiç yok (kapanışa direkt gidiyor); T-005'te ele alınmalı.

### N6. [Düşük] Bayat niyet değişkenleri geri dönüşte yanlış tetikleyebilir
- `negotiation_intent = proposal` (veya `confirmation_intent = revise`) değişkenleri bir sonraki girişte extraction yeni değer üretmezse bayat kalır; `confirm_record` ↔ `negotiate` arasında anlık sekme olabilir. Extraction her kullanıcı mesajından sonra çalışır, bu yüzden olasılık düşük, ama düşük güvenle değer atıldığında ("discarded value leaves no trace") oluşur. 
- **Düzeltme:** `revise` geçişinde bir kod düğümüyle niyet değişkenini sıfırla (sentinel `pending`) veya extraction enum'una `pending` ekle.

### N7. [Düşük] Adımlara yeniden girişte `on_enter` tekrar konuşturur
- `opening_unclear → opening` ve `confirmation_progress → confirm_record` yeniden girişlerinde `on_enter` (varsayılan `llm`) yeniden çalışır: açılış cümlesi tekrar söylenebilir; ikinci ürün öncesi gereksiz bir konuşma turu olabilir (Brief B: tüm sözler birlikte geri okunur, tek onay). `on_enter_first_entry_only` bu yolda sessizlik yaratacağı için kullanılmamalı; chat testinde gözlenmeli, gerekirse `loop_prompt` ile "devam et" kısa prompt'u.

### N8. [Bilgi] Ürün sayısı extraction'a bağlı
- `agreed_product_count` negotiate extraction'ından (integer, min_confidence 0.8) geliyor. Boş kalırsa `1`'e düşer (iyi varsayılan); ama 3 ürünlü müşteri 2 ürün için söz verirse yanlış sayıyla `confirm_record`'ta fazladan bir ürün beklenebilir. Sayı geri okuma ve onay anında kesinleşir; `confirm_record` extraction'ına da `agreed_product_count` eklenip son değeri o belirlemeli. Chat testi (Brief B "bazı ürünler" vakası) ile doğrulanmalı.

## Doğrulananlar

- Sabit sayı yok: `len(products)`; eşikler `max_attempts_per_product` ve `maxRetries = 1` dışında yalnızca `0/1` yapısal (sayaç karşılaştırmaları). Tek brief türevi sayı: N4.
- Hardcode: kaynak taramasında (alt dize) pratik brief değeri yok; spec alan adları spec'ten; kimlik alanları OpenAPI enum'una karşı doğrulanıyor.
- Yönlendirme sırası: deterministik geçişler özel yolların önünde (`opening`, `third_party`, `identity`, `negotiate`, `confirm_record`).
- Özel yollar: `available_in` dışında düğüm üretilmiyor (`identity` içinde `product_dispute` yok); `then=return` hedefi kaynak adım; `close` hedefi `closing`.
- Araç kapsamı korunuyor; `confirm_record` yalnızca `create_promise` (+ `response_mapping`), `closing` yalnızca `close_call`.
- Freya yok; testler çevrimdışı. Prompt şablonları `prompts.py`/`PROMPTS.md` içinde.

## Karar: düzeltme gerekli (küçük)
N1 ve N2 çok ürünlü ve yeniden deneme yolunu, yani all-or-nothing skorunda ağır basan vakaları, etkiliyor; ikisinin düzeltmesi birkaç satır (alan/değişken ayrımı, sentinel, normalize `ok`). N3 ve N4 aynı turda yapılabilir. N5–N8 chat testinden önce veya T-005 ile kapatılabilir. Düzeltmelerden sonra yeniden review ederim; Freya testi (onaylı, önce chat) bu düzeltmelerden sonra anlamlı olur.

---

# Fix2 kontrolü (N1–N4)

**Kapsam:** `builder/workflow.py`, `builder/spec.py`, `builder/tools_from_openapi.py` (post-hook), `tests/test_multi_step.py`, fixtures. N5–N8 T-005'e bırakıldı (kapsam dışı).
**Karar: merge edilebilir.** N1–N4 kapandı; 50 test geçiyor. Aşağıdaki üç not bloklayıcı değil: ikisi T-005'e, biri ilk onaylı chat testinde doğrulanacak.

## N1–N4 durumu

| # | Durum | Kanıt |
|---|---|---|
| N1 (model alanı ile `vars` çakışması) | **Kapandı** | Pre-hook artık `vars`'a hiçbir şey yazmıyor (`workflow.py:159-192`: yalnızca `config['body']`'yi yeniden yazıyor). `confirmation_progress` ürün numarasını `create_promise_args.<alan>` anahtarından okuyor (`:253`, `vars.get(number)`), yani `{{product_number}}` yer tutucusu adlı bir workflow değişkeni hiç oluşmuyor, yeniden girişte baked olmaz. Statik test: `test_model_product_field_is_never_written_as_a_workflow_variable` (`tests/test_multi_step.py:209`); sayaç testi artık `create_promise_args.selected_product_number` anahtarıyla çalışıyor (`:179,187`). |
| N2 (`is_set`/`pop`, 500'de sayaç) | **Kapandı** | `vars.pop` kalktı (kaynakta yalnızca `config` gövdesinde `body.pop` kaldı). `confirmation_progress` sonunda `vars['promise_result_ok'] = 'consumed'` (`:280`); `confirm_record → confirmation_progress` geçişi `promise_result_ok equals true/True/false/False` (`:474-477`), `is_set` değil: `consumed` yeniden tetiklemez. `opening_unclear` artık `vars[who_answered] = ''` yazıyor (`:238-246`). Post-hook HTTP hatasında, `status` hata ise, `error` doluysa, `ok` yoksa veya `data` dict değilse `data['ok'] = False` yazıyor (`tools_from_openapi.py` `_post_process_code`), böylece `response_mapping data.ok` 500'de de dolar ve `exhausted` yolu ulaşılabilir; test: `{"status_code": 500, …}` → "NOT carried out" (`test_vertical_slice.py:397`). |
| N3 (`closing` başarıyı `ok` ile ölçmeli) | **Kapandı** | `closing`: `close_call_response.data.ok` `equals true/True` → `end_call`; `close_call_failure_count > 1` → `end_call`; `ok false/False` → `closing` (yeniden dene); `always` → `closing`; `max_turn_transition="end_call"` (`workflow.py:493-509`). Test `test_account_and_closing_have_bounded_retries_and_confirm_can_revise`. |
| N4 (sabit "iki kez belirsiz" eşiği) | **Kapandı** | `opening.max_unclear_asks` spec alanı, pozitif tamsayı doğrulaması (`spec.py:230-232`); geçiş `greater_than (max_unclear_asks - 1)` (`workflow.py:409-412`). Fixture A/B: 2; synthetic: 3 (eşiğin koddan bağımsız olduğunu kanıtlıyor). Kaynakta artık brief türevi sabit sayı yok (kalan `0/1` karşılaştırmaları yapısal sayaçlar; `maxRetries = 1` ve `max_node_turns = 30` genel). |

## Yeni notlar (bloklayıcı değil)

1. **[Orta, T-005] `closing` yeniden deneme döngüsünün sınırı yalnızca HTTP sayacına bağlı.** `close_call_failure_count` büyük olasılıkla HTTP düzeyinde artıyor; banka `ok:false`'u HTTP 200 ile döndürürse (örn. geçersiz outcome/reason çifti) `ok false` → `closing` geçişi her yönlendirmede yeniden tetiklenir ve `max_node_turns` yalnızca kullanıcı turlarını saydığı için sınır işlemez; çağrı süresi dolana kadar sürebilir. Düzeltme: `closing` ile `close_call` arasında küçük bir sayaç kod düğümü (`close_attempts += 1`, ≥ 2 → `end_call`) veya post-hook'un `ok:false`'u `failure_count` yerine açıkça sayan bir değişkene yazması.
2. **[Düşük, T-005] Post-hook, `ok` alanı olmayan her yanıtı başarısız sayıyor.** `not ok_present → data['ok'] = False`. Kit API'sinde tüm yanıtlar `ok` içeriyor (güvenli), ama `ok` konvansiyonu olmayan bir gizli araç dosyası tüm başarılı çağrıları "NOT carried out" gösterir. Düzeltme: bu kuralı yalnızca OpenAPI 200 yanıt şeması `ok` alanını tanımlayan araçlar için üret (araç başına bayrak), diğerlerinde nötr cümle.
3. **[TO-CONFIRM, ilk onaylı chat testi] `vars` içinde `create_promise_args.<alan>` düz anahtarı.** Kit "model argümanları `<tool>_args.<field>` olarak değişken tablosuna yazılır" diyor (trial call), ancak bu anahtarın kod düğümünde `vars` sözlüğünde düz anahtar olarak mı yoksa iç içe sözlük olarak mı göründüğü doğrulanmamış. Anahtar yoksa ürün numarası boş kalır; sayaç `promise_attempts_` tek anahtarında birikir (çok ürünlü akış yine ilerler, ama "ürün başına iki deneme" ürünler arası karışır). Önlem: kod önce düz anahtarı, bulamazsa `vars.get('create_promise_args')` sözlüğünün `<alan>` değerini denesin (birkaç satır). Chat testinde gözlenecek: iki ürünlü Brief B vakasında `promise_attempts_1`/`promise_attempts_2` ayrı anahtarlarla oluşuyor mu.

## Doğrulananlar

- 50 test çevrimdışı geçti; Freya'ya istek atılmadı, kod değiştirmedim.
- Brief/fixture değeri taraması: kaynakta banka adı, tarih, tutar, outcome/reason adı, kuyruk adı, saat penceresi yok.
- Önceki turda kapanan yapılar (çok ürün sayacı, tek yeniden deneme, `available_in`/`then`, `opening` sayacı, sabit `3`'ün kalkması) bozulmadı.

## Karar: merge edilebilir
N1–N4 kanıtla kapandı. Not 3 ilk onaylı chat testinde (önce tek tur chat, sonra chat simülasyonu) doğrulanmalı; notlar 1 ve 2 T-005 ile birlikte ele alınabilir.
