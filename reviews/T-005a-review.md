# T-005a review (PUB-03 chat düzeltmeleri: F-019..F-022)

**Reviewer:** claude-reviewer · **Kapsam:** `tasks/T-005a-chat-fixes.md`, `tasks/T-005a-report.md`; `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`, `tests/test_multi_step.py`, `tests/fixtures/spec-*.json`, `docs/UAT-FINDINGS.md` F-019..F-023.
**Karar: merge edilebilir.** F-019..F-022 düzeltmeleri doğru kurulmuş, 60 test geçiyor, kapanış tek bir kod yolundan geçiyor ve yeni brief değeri yok. İki küçük düzeltme (bulgu 1 ve 2) Brief B / çok ürünlü testlerinden **önce** yapılmalı; PUB-03 yeniden testi bunlardan etkilenmiyor. F-021'in asıl nedeni hâlâ doğrulanmamış (TO-CONFIRM) ve F-012 (müşteri kapatırsa kayıt yok) açık kalıyor.

## Gözlemler (kanıt)

- `python3 -m unittest`: 60 test geçti. Freya'ya istek atılmadı, kod değiştirmedim.
- Üç fixture çevrimdışı render edildi. Not: synthetic spec'i kit OpenAPI'siyle render etmeye çalışınca `SpecError: outcomes are not in the close_call enum` aldım. Bu bir hata değil, yeni doğrulamanın çalıştığının kanıtı (synthetic'in kendi `close_call` enum'una sahip OpenAPI'si testte kuruluyor).
- Adım başına prompt tahmini (system + task + araç açıklamaları): A en büyüğü `identity` 481, B 454; hepsi 1.500 altında (alt sınır 500'ün altı, iskelet fixture'lar).
- Kaynak taraması (alt dize): `builder/*.py` içinde banka adı, tarih/tutar, outcome/reason adı, kuyruk adı, saat penceresi, "mobile app/branch" yok. Bu sözler yalnızca fixture'larda (spec verisi).

## İstenen kontroller

### 1. F-019..F-022 düzeltmeleri gerçekten doğru mu?

| Bulgu | Sonuç | Kanıt |
|---|---|---|
| F-019 (isim) | **Doğru** | `opening.address_with` spec alanı (boş olamaz, geçerli tanımlayıcı olmalı; `spec.py`). Render: "The person to ask for is {{title}} {{last_name}}. Use these words when you address them." Değişken adları kodda yok. |
| F-020 (yanlış cevap) | **Doğru, küçük bir boşlukla** | Kimlik şablonu dört sonucu ayırıyor: doğru → kısa onay, sıradaki soru; yanlış → "eşleşmedi", teşekkür etme, aynı soru, sıradakine geçme; işlem yapılmadı → aynı cevabı tekrar iste, yanlış sayılmaz; hak 0 → spec cümlesi, başka soru yok. Format artık "tool format, convert it yourself". Boşluk: bkz. bulgu 5 (son soru doğrulanınca "sıradaki soruyu sor" kuralı). |
| F-021 (yönlendirme bastırma) | **Tasarım makul, neden doğrulanmadı** | Aşağıda 3. |
| F-022 (kapanış) | **Doğru; bir önceliklendirme hatası var** | Aşağıda 2 ve bulgu 1. |

### 2. Kapanış artık kodla mı, `end_call`'a başka yoldan gidiliyor mu?

- Akış (kendi grafiğimle doğruladım, A ve B): her bitiş yolu `close_<durum>` kod düğümüne (`vars['close_state']` yazar) → `closing` (kod: tablodan outcome/reason/cümle) → `closing_say` (sabit `tts` satırı `{{closing_say}}`) → `close_attempt` (sayaç) → `close_record` (engine `api_request`, `close_call` baked `{{close_outcome}}`/`{{close_reason}}`) → `end_call`.
- `end_call` yalnızca `close_record`'dan gelen geçişlerle ulaşılıyor (öncüller: `['close_record']`). `close_record` yalnızca `close_attempt`'tan; `closing_say` yalnızca `closing`'den; `closing` yalnızca `close_*` düğümlerinden. Hiçbir sohbet adımında `close_call` aracı yok (`workflow_tools_by_step`: `close_record: close_call (engine)`). Tur sınırı (`max_turn_transition`) da `close_turn_limit` → aynı yola gidiyor.
- Sınırlı yeniden deneme doğru: `close_attempt` önce sayacı artırır, `close_record` ok `true/True` → `end_call`; değilse `close_attempts > 1` → `end_call` (başarı iddiası yok), aksi halde bir kez daha. `close_attempt` her seferinde `close_call_ok`'u `''` yapıyor, yani bayat `true` ikinci denemeyi etkilemez.
- Kapanış cümlesi `close_call`'dan önce söyleniyor (Brief A kural 47 ile uyumlu); `close_call` başarısız olursa model "kaydedildi" diyemez çünkü cümleyi model değil spec yazıyor.
- Eşlenmemiş bitiş durumu: spec yüklenirken hata (`outcomes[].on does not map …`); outcome değeri `close_call` enum'unda yoksa render hatası (iyi: sessiz yanlış kayıt yok).

### 3. Kendine dönen `always`'ın kaldırılması kit dokümanıyla uyumlu mu?

- **Uyumlu.** `workflow-format.md` "Order of evaluation": "4. nothing matched: stay in the node, wait for the next user message"; "Self-transition … Prefer this to `loop_condition`" bir **tercih** olarak geçiyor, zorunluluk değil. Zorunlu `always` kuralı yalnızca passthrough düğümler için ("Every passthrough node ends with an `always` transition"). Kit'in `examples/base-agent.json` dosyasında da sohbet düğümlerinde kendine dönen geçiş yok (kontrol ettim).
- Kendi geçmiş notumu düzeltiyorum: T-001 review bulgu 8'de self-`always` eklenmesini önermiştim; bu T-005a ile geri alınmış durumda ve kit ile çelişmiyor. `docs/STARTER-KIT-FACTS.md` satırı ("A node needs an `always` fallback; passthrough nodes must end with one") yanlış genelliyor, "passthrough düğümler `always` ile bitmeli; sohbet düğümü eşleşme yoksa yerinde kalır" biçiminde düzeltilmeli (belge sahibi CTO).
- **Doğrulanmamış:** "Missing prior assistant message" bastırmasının self-loop'tan kaynaklandığı bir hipotez; log'daki `node_enter identity from identity` ile uyumlu ama kanıt değil. Self-loop kalkınca hâlâ bastırılıyorsa, karar verici sonuçlar (doğrulandı, hak bitti, söz kaydedildi, kapanış) bir kullanıcı turu gecikir. Raporun yedek katmanı (kimlik prompt'u hak bitince kendisi söylüyor) hak-bitti vakasını korur. Kalan etki: kapanış zinciri yalnızca bir yönlendirme olayıyla başlıyor; son cümleden sonra müşteri yanıtlamazsa (veya kapatırsa) zincir başlamaz ve kayıt düşmez. Bu F-012 ile aynı aile; T-005 kapsamındaki "end-of-call lifecycle" yedeği hâlâ gerekli.

### 4. Sızıntı testi izin listesi genişlemesi (`title`, `last_name`, bitiş durumu adları) kabul edilebilir mi?

- **Kabul edilebilir**, iki iyileştirmeyle (bulgu 6):
  - `title`/`last_name` artık elle yazılmıyor, `CALL_VARIABLES` sabitinden türetiliyor (`allowed_fixed_tools | CALL_VARIABLES`); bunlar kit sözleşmesi (`STARTER-KIT-FACTS.md`: her çağrıda bulunan değişkenler), brief verisi değil.
  - Bitiş durumu adları (`identity_failed`, `promise_recorded`, `promise_failed`, `callback_scheduled`, `opening_unclear`, `default`, `OPTIONAL_CLOSE_STATES`) iskeletin kendi sözlüğü; spec bunlara `on` ile başvuruyor. Bunlar brief'in outcome/reason adlarıyla çakışmıyor.
- Taramanın zayıflığı sürüyor: yalnızca tam eşleşme; bir brief kelimesi izin listesindeki bir sözcükle aynıysa gizlenir (örn. `failed` zaten izinli ve Brief A'da `not_verified/failed` reason'ı var; kodda `failed` iz günlüğü durumu olarak kullanılıyor). Ben ayrıca alt dize taraması yaptım: sızıntı yok.

### 5. Yeni hardcode var mı?

- **Yok** (alt dize taraması). Yeni sabit sayılar yapısal: `close_attempts > 1` (en çok 2 deneme), `maxRetries = 1` (bkz. bulgu 2), `max_node_turns = 30`. Kapanış sözü `CLOSING_FALLBACK_SAY` ("Thank you for your time. Goodbye.") genel ve `prompts.py`/`PROMPTS.md` içinde. `turn_limit`, `account_failed`, `callback_failed` durumlarının outcome eşlemesi fixture'da (spec); koda yazılı değil.

## Bulgular (önem sırasıyla)

### 1. [Orta, Brief B / çok ürün öncesi düzeltilmeli] Kayıtlı söz varken kapanış sonucu yanlış önceliklendiriliyor
- `builder/workflow.py` `_closing_code`: `candidates = [state]`, ancak durumun kendi tablo satırı yoksa `promise_recorded` ekleniyor. Durum için satır **varsa** o kullanılıyor. Çalıştırarak doğruladım (A ve B fixture'ları): `close_state = promise_failed` ve `promise_recorded_count = 1` → `no_promise / service_error`; `negotiation:<ret>` ve 1 kayıt → `no_promise / refused`.
- Brief B: "`promise` wins whenever at least one promise was recorded, except rule 10 (transfer)" ve kural 11 ("bir ürün iki kez başarısız olursa kaydedilenleri koru"). Yani bir ürün kaydedilmiş, diğeri başarısız/reddedilmişse doğru outcome `promise`; mevcut kod `no_promise` yazar (ledger uyuşmaz). Kural 10: transfer her zaman kazanır, bu şu an doğru (özel yol durumu önce aranıyor).
- **Düzeltme (genel):** outcome satırına `wins_over_promise: true/false` (varsayılan false) ekle; kod: `recorded > 0` ve seçilen satır `wins_over_promise` değilse `promise_recorded` satırını seç (transfer satırlarında true). Brief A'da sonuç değişmez (tek ürün). Test: B fixture'ında `promise_failed` + 1 kayıt → `promise`.
- Not: B'de kural 11'in `add_note(service_error)` yarısı hâlâ eksik (T-005 açık).

### 2. [Orta] `close_call` için `maxRetries: 1` yazma aracı kuralını çiğniyor
- `workflow.py` `_close_tool`: `config.maxRetries = 1` + düğüm seviyesinde 2 deneme = başarısızlıkta en çok 4 `close_call` çağrısı. `docs/FREYA-INTEGRATION.md`: "Write tools get `maxRetries: 0` at the tool level; retry decisions are made in the flow". Brief A kural 46: "exactly one `close_call`"; yeniden deneme bankada çift kayda yol açabilir (özellikle banka 500 yerine kaydı yazıp zaman aşımı verirse).
- **Düzeltme:** `maxRetries: 0`; yeniden deneme yalnızca `close_attempt` döngüsünde (zaten var).

### 3. [Orta, TO-CONFIRM] Sabit kapanış cümlesi ve engine çağrısı sırası
- `closing_say` bir passthrough **kod** düğümü ve `on_enter: {"type":"tts","text":"{{closing_say}}"}` ile cümleyi söylüyor; kit passthrough düğümler için "silent veya kısa sabit satır" diyor (uyumlu), ama chat modunda sabit satırın gerçekten konuşulup konuşulmadığı ve `close_call`'dan önce görünüp görünmediği doğrulanmadı (raporun TO-CONFIRM 2'si). `close_reason` hiç set edilmediğinde alanın istekten düşmesi (TO-CONFIRM 3) ve `data.ok`'un `close_record` düğüm `response_mapping`'inde dolması (TO-CONFIRM 4) de doğrulanmalı.
- Kozmetik: hak bitince kimlik adımı ve kapanış cümlesi aynı uyarıyı iki kez söyleyebilir; `confirm_record` kayıt cümlesi ve kapanış cümlesi de örtüşebilir. Çözüm gerekirse outcome satırına `already_said` durumları (spec).

### 4. [Düşük] Düğüm adı ve değişken adı aynı: `closing_say`
- Düğüm `closing_say` ve değişken `{{closing_say}}` aynı ad. Ad uzayları ayrı olduğundan çalışır (otomatik anahtarlar `closing_say_response.*` düğüm adına bağlı), ama karışıklık riski var; değişkeni `closing_sentence` yapmak güvenli.

### 5. [Düşük] Kimlik şablonunda son soru sonrası belirsizlik
- "verified is true: acknowledge briefly and ask the next question." Son soru doğrulandığında sıradaki soru yok; F-021 gecikmesi sürerse model uydurma bir soru sorabilir. 
- **Düzeltme (genel şablon):** "If it was the last question, ask nothing more; say the answers matched" (teşekkür/devam cümlesi; hesap bilgisi söyleme).

### 6. [Düşük] Sızıntı testinde izin listesi türetilmeli
- Bitiş durumu adları testte elle yazılmış (`"opening_unclear", "callback_scheduled", …`) ve `spec.py` string sabitlerinin kopyası. `spec.py`'de tek bir `CLOSE_STATE_NAMES` dışa aktarımı ve testin ondan türetmesi izin listesinin sessizce genişlemesini önler. Ayrıca `failed`, `default`, `return` gibi genel sözcükler yalnızca belirli dosyalarda izinli sayılabilir (dosya bazlı kapsam).

### 7. [Düşük, T-006 notu] Fixture A'da `turn_limit` → `service_error`
- Tur sınırına takılan çağrı (müşterinin konuşmayı uzatması) `no_promise/service_error` olarak kaydedilir; bu bir servis hatası değil. Extractor brief'ten alamazsa `default` satırı kullanılmalı, `service_error` yalnızca gerçek hata durumlarına (`account_failed`, `promise_failed`) bağlanmalı. (Fixture kararı, kod değil.)

## Açık kalanlar (kapsam dışı, bilgi)

- **F-012** (müşteri kapatırsa kayıt yok): kapanış zinciri yalnızca yönlendirme olayıyla başlıyor; end-of-call lifecycle yedeği henüz yok (ek olarak F-021 gecikmesi bunu daha olası kılıyor).
- Kural 15 (kimliği reddetme, `not_verified/declined`) hâlâ ayrı bir yol değil; başarısız geri arama tekrar denenmeden kapanıyor (rapor açık sorusu 3).
- F-023 (503/504): platform kaynaklı olabilir; sonraki onaylı chat testinde tek otomatik yeniden deneme önerildi.

## Karar: merge edilebilir
F-019..F-022 düzeltmeleri doğru ve kapanış mühendisliği (kodla seçim, tek `end_call` yolu, sınırlı yeniden deneme, dürüst başarısızlık) sağlam. **Bulgu 1 ve 2** küçük ve genel; Brief B / çok ürün testlerinden önce kapatılmalı. Sonraki onaylı chat testinde sırayla gözlenecekler: self-loop kalkınca "Suppressed: Missing prior assistant message" kayboldu mu, `closing_say` cümlesi `close_call`'dan önce konuşuldu mu, `close_reason` boşken alan düştü mü, `close_record` `data.ok`'u doldurdu mu.

---

# Fix kontrolü (T-005a-fix: bulgu 1, 2, 4, 5, 6, 7)

**Kapsam:** `tasks/T-005a-fix-report.md`; `builder/spec.py`, `builder/workflow.py`, `builder/prompts.py`, `tests/test_multi_step.py`, fixtures. Bulgu 3 (TO-CONFIRM) chat testine bırakıldı, kapsam dışı.
**Karar: merge edilebilir.** Altı bulgunun hepsi kanıtla kapandı; 62 test geçiyor; yeni hardcode yok. Freya'ya istek atılmadı, kod değiştirmedim.

## Bulgu durumu

| # | Durum | Kanıt |
|---|---|---|
| 1 (söz kayıtlıyken kapanış önceliği) | **Kapandı** | `spec.py`: `outcomes[].wins_over_promise` (isteğe bağlı, varsayılan false, boolean olmayan değer SpecError; test `test_wins_over_promise_must_be_boolean`). `workflow.py` `_closing_code`: önce durumun kendi satırı, sonra `recorded > 0 and not chosen[4]` ise `promise_recorded` satırı. Üretilen kodu çalıştırdım: B'de `promise_failed` + 1 kayıt → `promise`; `negotiation:no_arrangement` + 1 kayıt → `promise`; `special:human_transfer` + 1 kayıt → `transferred/human` (transfer kazanıyor); kayıt 0 iken `promise_failed` → `no_promise/service_error`. A için aynı davranış (`special:human` fixture'da `wins_over_promise: true`). |
| 2 (`close_call` `maxRetries`) | **Kapandı** | `_close_tool`: `config.maxRetries = 0` (render çıktısı: `{'timeoutMs': 10000, 'maxRetries': 0}`, A ve B); yeniden deneme yalnızca `close_attempt` döngüsünde (en çok 2 çağrı). Test (`tests/test_multi_step.py:284`). `get_account` için `maxRetries: 1` kalıyor (salt-okuma, kural uyumlu). |
| 4 (düğüm/değişken adı) | **Kapandı** | Değişken `closing_sentence`; düğüm `closing_say`; `on_enter` `{{closing_sentence}}` (test `:283`); `closing` kodunda eski `vars['closing_say']` kalmadı. |
| 5 (son kimlik sorusu sonrası) | **Kapandı** | `prompts.py:152`: "After the last question, ask nothing more; say the answers matched and give no account details yet." Test `:302`. |
| 6 (izin listesi türetme) | **Kapandı, kısmi** | `spec.py` `CLOSE_STATE_NAMES` tek sabit; sızıntı testi `set(CLOSE_STATE_NAMES)` kullanıyor (`:532`), elle liste yok. Dosya bazlı kapsam (öneri) yapılmadı: `failed`, `default`, `return` hâlâ her dosyada izinli. Düşük risk (alt dize taramam temiz); isteğe bağlı iyileştirme olarak kalıyor. |
| 7 (`turn_limit` eşlemesi) | **Kapandı** | A ve B fixture'larında `turn_limit` artık `default` satırına düşüyor (çalıştırdım: `turn_limit` → `no_promise/refused`, çözülen durum `default`); `service_error` yalnızca `promise_failed`/`account_failed`'da. Test `:236`. |

## Yeni hardcode taraması

- `builder/*.py` alt dize taraması (banka adı, tarih/tutar, outcome/reason adı, kuyruk adı, saat penceresi, "mobile app/branch"): **temiz.**
- Yeni sabitler yapısal: `CLOSE_STATE_NAMES` (iskelet sözlüğü), `wins_over_promise` (spec alanı, brief değeri kodda yok), `maxRetries 0/1`. Brief'e özgü sayı veya sözcük eklenmedi.

## Notlar (bloklayıcı değil)

- **T-006 için:** `wins_over_promise` ve `default` satırı seçimi artık extractor'ın brief'ten çıkaracağı alanlar (rapor açık sorusu 3 doğru). Brief'te "transfer her zaman kazanır" gibi bir cümle yoksa varsayılan `false` kalır; bu da hiçbir satırın promise'ı ezmemesi demek, yani yalnızca açık kural varsa bayrak true olmalı.
- **Bulgu 3 ve F-012** (açık kalanlar): ilk onaylı chat testinde gözlenecek maddeler değişmedi (sabit cümle `close_call`'dan önce söyleniyor mu, `close_reason` boşken alan düşüyor mu, `close_record` `data.ok`'u dolduruyor mu); müşteri kapatırsa kayıt yazılması hâlâ end-of-call yedeğini bekliyor. `add_note(service_error)` (Brief B kural 11) T-005'te.

## Karar: merge edilebilir
Bulgular 1, 2, 4, 5, 6 ve 7 kapandı; yeni hardcode yok. Brief B / çok ürün chat testlerine geçilebilir.
