# T-004 review (multi-step skeleton from a spec)

**Reviewer:** claude-reviewer · **Kapsam:** `tasks/T-004-multi-step-skeleton.md`; `builder/spec.py`, `builder/workflow.py` (`build_spec_workflow` ve yardımcılar), `builder/prompts.py` (adım şablonları), `builder/build.py` (`--spec`, trace), `tests/test_multi_step.py`, `tests/fixtures/spec-*.json`. T-003-fix kaynaklı değişiklikler (post-hook metinleri, `tools_from_openapi.py`, sistem prompt'u) bulgu sayılmadı. (İnceleme sırasında `tools_from_openapi.py` kısa süre sözdizimi hatalıydı; Codex düzeltince bekleyip yeniden koştum, sonuçlar bu sonrası: 44 test geçti.)
**Karar: düzeltme gerekli.** İskelet (adımlar, araç kapsamı, tool-sonucuna bağlı geçişler, product-id hook'u, tek `end_call`) doğru kurulmuş ve brief/fixture değeri kodda yok (tek istisna: hook'ta `3`). Ama `confirm_record` çıkışı Brief B'yi ve PUB-10'daki yeniden denemeyi yapısal olarak bozuyor (bulgu 1), ve `opening`'in kapanışa çıkışı yok (bulgu 2). İkisi de küçük düzeltme; T-005'ten önce yapılmalı.

## Gözlemler (kanıt)

- Fixture A/B/synthetic spec'leri çevrimdışı render ettim (Freya yok): 
  - Adımlar (A): `opening, third_party, identity, account (api_request), negotiate, confirm_record, closing, end_call, special_already_paid, special_dispute, special_human`.
  - Araçlar: `third_party: schedule_callback`, `identity: verify_identity`, `confirm_record: create_promise`, `closing: close_call`, `special_human: transfer_to_agent` (B'de `special_product_dispute: add_note`); `opening/negotiate/account/diğer special`: araç yok. `account` node'u `get_account`'u `pre_actions` ile çalıştırıyor, `response_mapping` node seviyesinde.
  - Adım başına prompt tahmini (system + task, karakter ÷ 4): A: opening 184, third_party 125, identity 171, negotiate 146, confirm_record 141, closing 321, special 126–135; B: 124–312; synthetic: 93–169.
- Kaynak taraması: `builder/*.py` içinde pratik brief değeri (tatil tarihi, tutar, outcome/reason adı, kuyruk adı, banka adı, saat penceresi) yok. Tek sabit brief türevi: `workflow.py:174` `min(len(products), 3)` (Brief B "en fazla üç ürün" bilgisi, bkz. bulgu 4). Sabit araç adları yalnızca `FIXED_TOOL_NAMES` ile izinli yerde.
- Her yol kapanış adımına bağlanıyor ve tek `end_call` düğümüne yalnızca `closing` ulaşıyor (test `test_reachability_and_terminal_shape`). Tüm düğümlere erişilebilir. `null`/`agent_config` yok, `name == key`, `tools` yalnızca conversation düğümlerinde.
- Freya'ya istek atılmadı, kod değiştirmedim.

## Bulgular (önem sırasıyla)

### 1. [Yüksek / bloklayıcı] `confirm_record` ilk `create_promise` sonucunda çıkıyor → çok ürünlü kayıt ve tek yeniden deneme imkânsız
- `builder/workflow.py:357-360`: `create_promise_success_count > 0` **veya** `create_promise_failure_count > 0` → `closing`. Tool sonucundan sonra yönlendirme aynı turda yeniden çalışır (tools-and-code.md "Routing on tool results"), yani:
  - **Brief B** ("her ürün için bir kez `create_promise`"): ilk ürünün kaydından sonra adım kapanışa gider; 2. ve 3. ürün hiç kaydedilmez (kayıt eşleşmez, vaka düşer). Bu 3 vaka ve gizli brief'lerdeki çok ürünlü vakaların hepsi.
  - **PUB-10 / Brief A kural 37** ("başarısız olursa bir kez daha dene"): ilk başarısız çağrı (`failure_count == 1`) adımı hemen kapatır; `closing` adımında `create_promise` yok, yeniden deneme olanaksız. Ayrıca `closing` modeli outcome'u kendisi seçiyor (`promise` mu `service_error` mu), kayıt başarısız olduğu hâlde yanlış seçerse dürüstlük kaybı olur.
  - Sayaçlar çağrı boyunca birikir (`*_success_count` sıfırlanmaz), bu da bir sonraki kullanımlarda yanlış tetikleme riski doğurur.
- **Düzeltme (genel, brief değeri yok):** çıkışı "kaç ürün için onay alındı"ya bağla. Örn. spec'e `confirmation.expected_count_variable` ekle; `negotiate`/`confirm_record` extraction'ı bir `agreed_product_count` (integer) çıkarsın veya account hook'u `len(products)`'ı bir değişkene yazsın. Çıkış: `create_promise_success_count >= agreed_count` (iki ayrı `greater_than agreed_count-1` yerine, ayrıca kod düğümüyle `promises_remaining` string/int değişkeni hesaplayıp `equals "0"`). Hata için: ürün başına en fazla 2 deneme sayacı (`pre_process_code` ile `vars['promise_attempts_<n>']`) ve yalnızca ikinci başarısızlıkta çıkış; ilk başarısızlıkta adım kalır ve post-hook yeniden denemeyi söyler. `confirm_record` içinde `add_note` gerekiyorsa (Brief B kural 11) ayrıca araç olarak sunulmalı (şu an yok, bkz. bulgu 6).
- Test: `test_tools_are_scoped` kapsam doğruluyor ama bu yönlendirmeyi hiç sınamıyor. Eklenmeli: spec B, 2 ürünlü hesap; "ilk başarılı çağrıdan sonra `confirm_record`'dan çıkılmaz" (koşul değerlendirme simülasyonu).

### 2. [Yüksek] `opening`'den kapanışa çıkış yok; `unclear` yanlışlıkla `third_party`'ye gidiyor
- `builder/workflow.py:274-285`; fixture A: `third_party_values = ["third_party", "unclear"]`.
- Brief A kural 3: cevap belirsizse bir kez daha sor, hâlâ belirsizse `not_reached/unclear` ile kapat. Burada `unclear` ilk "Hello"da hemen `third_party`'ye yönlendiriyor (ikinci sorma yok), orada geri arama planlanıyor (`not_reached/callback` ya da hiç kapanış). `opening`'in `closing`'e hiçbir geçişi yok; yalnızca 30 tur sınırı. Müşteri onay vermeyip konuşmayı sürdürürse ya da reddederse (kural 45) adım kilitlenir.
- **Düzeltme:** `opening.close_values` (kapanışa gider) ve `opening.stay_values` (`unclear`, döngü) ayrı listeler olsun; "ikinci belirsizlik" için sayaç değişkeni (`opening_unclear_count`, post-extraction hook veya kod düğümüyle) `greater_than 1` → `closing`. Fixture'dan `unclear`'ı `third_party_values`'tan çıkar.

### 3. [Orta] Özel yollar her adımda aktif ve hepsi kapanışa bağlı → "devam eden" yolları ifade edemiyor
- `workflow.py:266-275,312,324,345,356`; `:378-396`.
- Tüm `special_paths` her adımın (opening, third_party, identity dahil) geçişlerine `matches_intent` ile ekleniyor ve her özel düğüm `closing`'e gidiyor:
  - Brief A kural 43/4 ("scam mı?", "robot musun?"): cevapla ve **devam et**. Burada bu yollar kapanışa gider; bu soru yüzünden görüşme biter (fixture bunları zaten içermiyor; "yan konuşma, soru geri sorma" gizli müşteri profilinde yaygın).
  - Kural 39/40/32 (ödedim, itiraz, zorluk) kimlik doğrulamasından **sonra** geçerli; `identity`'de `special_dispute` tetiklenirse görüşme doğrulama olmadan `no_promise/dispute` ile kapanır (kural 45: doğrulama öncesi `not_verified/declined` olmalı) ve spec'in `say` metni borç bilgisi içerebilir.
  - Özel yolun `outcome/reason`'ı render'da hiç kullanılmıyor (yalnızca doğrulanıyor); kapanış sonucu `closing`'deki modelin tabloya bakarak seçimine bırakılmış.
- **Düzeltme:** spec'te her yol için `available_in` (adım listesi, varsayılan `negotiate, confirm_record`) ve `then` (`close` veya `return`) alanı; `return` için `__previous__` hedefi. `close` yollarında `closing` adımına kapanış değeri aktarılsın (bkz. bulgu 5).

### 4. [Orta] Product-id hook'unda sabit `3` ve doğrulanmamış `vars` biçimi
- `builder/workflow.py:174`: `0 <= index < min(len(products), 3)`. Brief B'ye özgü "en fazla üç ürün" bilgisi koda gömülmüş; gizli brief'te 4 ürün olabilir, o zaman 4. ürün için hook çalışmaz ve API `ok:false` döner. Test de `4`'ün reddedilmesini bekliyor (`test_product_hook_maps_first_three_and_never_raises`). AGENTS.md öncelik 1 gereği kaldır: `0 <= index < len(products)`.
- `vars.get(products_variable)`: node seviyesindeki `response_mapping` ile yazılan listenin `vars` içinde hangi biçimde olduğu kit'te doğrulanmamış ("exact form … is not confirmed"). Hook liste ve JSON-string'i işliyor, düzleştirilmiş anahtarları (`get_account_response.data.products…`) işlemiyor. Boş kalırsa sessizce hiçbir şey yapmaz, gövdede `product_number` kalır ve API reddeder (dürüst başarısızlık ama kayıt düşer).
- **Düzeltme:** `vars` için üç kaynağı sırayla dene (mapped değişken, JSON-string, `get_account_response.data.products` düz anahtarı); hiçbiri yoksa hook `config['body']['product_id']`'ı boş bırakmasın, ilk (ve tek) ürünün kimliğini kullanmasın. Gerçek biçim chat testinde teyit edilmeli (**[TO-CONFIRM]**, onaylı chat).
- Ürün numaralaması: araç açıklaması "1-based product number from the account list shown in this call" diyor, ama listenin numaralı bir gösterimi yok (ham JSON). T-005 `account` kodu numaralı kısa özet üretecek; o zamana kadar belirsiz.

### 5. [Orta] `closing` adımı sonucu modele bırakıyor; kimlik-başarısızlığı/tarih sözleri kapanışta kayboluyor
- `workflow.py:363-370`, `prompts.py` `CLOSING_TASK_TEMPLATE`.
- Kapanış adımı yalnızca `outcome=…; reason=…; when=…` tablosunu görüyor. Önceki adımın kuralları (ör. 3 yanlıştan sonra "mobil uygulama/şube" cümlesi, `identity` kuralı) yeni adıma geçmiyor; tool sonucu yönlendirmesi aynı turda `closing`'in prompt'unu devreye alıyor. Kimlik tükendi → `closing` "ne söyleyeceğini" bilmiyor.
- `closing → closing` döngüsünde `close_call` başarısız olursa sınırsız tekrar (sadece 30 tur sonrası `max_turn_transition = "closing"` yine kendisine, `_conversation` hepsine "closing" yazıyor: kendine döngü). Çağrı süresi bitene kadar sürer.
- **Düzeltme:** (a) spec'te her outcome için `say` (kapanışta söylenecek cümle); (b) `close_call_failure_count > 1` → `end_call` (dürüst kayıtsız çıkış, trace uyarısı); (c) `closing` düğümünde `max_turn_transition: "end_call"`. (d) T-005 sonrası kapanış çıktısı kodla hesaplanacak (F-012).

### 6. [Orta] Eksik araç/geçiş: `confirm_record` iptal/değişiklik ve `account` hatası
- `confirm_record` yalnızca `create_promise`'ı sunuyor ve tek çıkışı araç sonucu. Müşteri geri okumada tarihi/tutarı değiştirir (kural 35) ya da reddederse `negotiate`'e dönüş yok; `negotiate` kuralları bu adımda yok. Adım 30 tura kadar döner, sonra `closing`.
- `account` düğümünde `get_account` başarısız olursa (`500, may be repeated`) `always` ile `negotiate`'e geçer; ürün listesi boş, model uydurabilir. `maxRetries` 0 (T-001'den). 
- **Düzeltme:** `confirm_record` → `negotiate` geri geçişi (extraction enum `revise`) ve `account` düğümüne `get_account_failure_count > 0` → bir kez yeniden deneme (kendine) ardından `closing`. Okuma-yazma ayrımı: `pre_actions` salt-okuma çağrısına `maxRetries: 2` verilebilir (docs).

### 7. [Düşük] Geçiş sırası: `matches_intent` hepsinin önünde
- Her adımda özel yollar (`matches_intent`) listenin başında, deterministik koşullar (`identity_verified`, sayaç) sonra. Docs: deterministik koşullar önce değerlendirilir ama "specific first, broad last / deterministic before matches_intent" tasarım kuralı var. Doğrulama sonucunda aynı turdaki son kullanıcı mesajı yanlışlıkla `matches_intent` ile eşleşirse özel yola sapılır.
- **Düzeltme:** deterministik geçişleri özel yollardan önce yaz.

### 8. [Düşük] Test boşlukları
- `test_freya_extraction_and_passthrough_wire_shapes` içindeki `assertNotEqual("is_tool_call", transition["condition"]["operator"])` anlamsız (anahtar `is_tool_call` geçişte, koşulda değil): `special_dispute` geçişi `is_tool_call: True` kullanıyor ve test bunu denetlemiyor.
- Brief taraması (`test_builder_string_literals_do_not_embed_fixture_values`) yalnızca tam eşleşen ≥4 karakterli string sabitlerini yakalıyor (alt dize yok); `3` gibi sayıları, "up to three" gibi türev bilgiyi yakalamaz. Alt dize + sayı kontrolü ve brief metni (`briefs/*.md`) kelime taraması eklenmeli.
- `test_fixture_a_prompts_are_under_budget` yalnızca üst sınırı (≤1500) denetliyor; alt sınır (500) ve araç açıklamaları dahil değil. Fixture A'da her adım 125–321 token: alt sınırın altında, çünkü fixture yalnızca 9 kural içeriyor (brief A'da 47). Negotiate adımı "apply the brief's date, floor, and refusal rules" diyor ama brief bu iskelette modele verilmiyor → prompt hiçbir şeye işaret ediyor. Bu T-006 sonrası kapanır; o zamana kadar chat sonuçları iskeletin değil fixture'ın eksikliğini ölçecek (not).
- Tüm özel yolun bir yolu `tool == ""` + `is_tool_call` geçişi için test yok.

## UAT F-008..F-012 yapısal karşılama

| Bulgu | Durum | Gerekçe |
|---|---|---|
| F-008 (uydurma product id) | **Yapısal olarak karşılandı** (hook biçimi doğrulanacak) | Model `product_number` (integer) veriyor, id `pre_process_code` ile hesaplanıyor (`workflow.py:156-203`). Açıklar: bulgu 4 (`3` sınırı, `vars` biçimi, numara listesi). |
| F-009 (doğrulama sonrası araç yeniden çağrısı) | **Karşılandı** | `verify_identity` yalnızca `identity` adımında; `all_verified` ("true"/"True") gelince `account`'a çıkılıyor, araç artık yok. |
| F-010 (yanlış cevap, "teknik sorun", erken `get_account`) | **Kısmen** | ✔ `get_account` yalnızca `account` düğümünde (`pre_actions`), kimlik doğrulanmadan çağrılamaz; ✔ çıkış `wrong_answers_left < 1` ile araç sonucundan; ✔ üç yanlıştan sonra doğrulama durur. ✘ "Cevabı kendiliğinden yeniden gönderme"/"teknik sorun" iddiası hâlâ prompt+post-hook meselesi (T-003-fix); ✘ kimlik tükenince `closing`'e geçince söylenecek cümle (bulgu 5). |
| F-011 (yanlış bant, tatil) | **Karşılanmadı** (T-005 kapsamı) | Hesaplama yok; negotiate prompt'u fixture'da "apply the brief's rules" diyor. |
| F-012 (müşteri kapatınca kayıt yok) | **Karşılanmadı** (T-005 kararı) | Task metni de ertelemişti; kapanış yalnızca model aracı. |
| F-001 / F-004 (üçüncü kişi, transfer sözü) | **Büyük ölçüde karşılandı** | `third_party`/`special_human` çıkışı araç sonucuna bağlı (`schedule_callback_*`, `transfer_to_agent_*`). Açık: `opening`'de `unclear` yolu (bulgu 2) ve sonuç seçimi hâlâ `closing` modelinde (bulgu 5). |

## Doğrulananlar

- **Brief/fixture sızıntısı (en kritik):** kaynak taramasında (alt dize) banka adı, tatil/tarih, tutar, outcome/reason, kuyruk adı, saat penceresi yok; spec alan adları (`who_answered_variable`, `products_variable`, `product_number_field`, `promise_product_id_field`) spec'ten geliyor; kimlik alanı enum'a karşı doğrulanıyor (`workflow.py:239-250`). Tek ihlal: `3` (bulgu 4). Özel yol araç adlarının `FIXED_TOOL_NAMES` dışına çıkması ve `verify_identity/get_account/create_promise/close_call` rezerve olması denetleniyor.
- **Araç kapsamı:** her araç yalnızca kendi adımında (test + kendi render kontrolüm). `special_*` düğümlerinde yalnızca baked argümanlı tek araç; `queue` gibi alanlar `default` ile sabitlenmiş (`_tool_with_baked_args`), `required`'dan çıkarılıyor.
- **Yönlendirme:** `identity` → `all_verified` (`"true"`/`"True"`), `less_than 1`; `third_party`/special araç çıkışı sayaçlarla; extraction'larda `enum_values` + `min_confidence: 0.8`.
- **Hook güvenliği:** `product_id_pre_process_code` `compile` ediliyor, `{{`/`}}` yok, hatalı girdide yükseltme yok (testte `None`, `""`, `"x"`, `0`, `4`, `{}`, `[]`).
- **CLI/trace:** `--spec` yoksa tek adımlı yedek ve trace'te açıkça yazıyor; trace adımları, adım başı araçları ve prompt tahminlerini yazıyor, `>1500` için `warning:` satırı; `SpecError` kullanıcı hatası olarak (rc 2) işleniyor.
- **Prompt'lar:** yeni şablonlar `prompts.py`'de ve `PROMPTS.md`'de (tek yer ilkesi). Yer tutucu doldurma `render_prompt` ile tek geçişli değil ama şablonlarda iç içe yer tutucu yok (bilgi).
- **Freya kuralı:** hiçbir istek atılmadı; testler çevrimdışı.
