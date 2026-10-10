# Kit v3 uyum kontrolü

**Tarih:** 2026-10-10 · **Kontrol eden:** CTO (Claude) · **Kaynak:** `build-the-builder-v2/README.md` (kit v3) ve `build-the-builder-v2/docs/` (`workflow-format.md`, `tools-and-code.md`, `api.md`)

**Yöntem:** README ve üç doküman okundu. Builder'a Brief A ve Brief B için workflow ürettirildi (`--print --spec tests/fixtures/spec-brief-{a,b}.json`, Freya'ya istek yok). Çıktı dokümanlardaki kurallara karşı bir script ile kontrol edildi.

**Özet:** Workflow yapısı ve Freya kullanımı dokümanlara uyuyor. README'ye göre 3 eksik var; biri finalde kural ihlali olur. Dokümanlara göre 4 küçük prompt eksiği var.

## README bulguları

### R-1. Spec elle yazılıyor (kritik, finalde kural ihlali)

- **Durum:** Çok adımlı ajan sadece `--spec tests/fixtures/spec-brief-a.json` ile kuruluyor. Bu spec brief'ten elle yazıldı. `--spec` verilmezse resmi komut (`build.py {brief} {tool_api}`) tek adımlı, zayıf ajana düşüyor. `submission/brief-a.workflow.json` da elle yazılmış spec'ten kuruldu.
- **README kuralı:** Builder final brieflerinde "hiçbir elle adım olmadan" bir kez çalışır. Final brief'ten hiçbir kural, değer ya da isim koda yazılamaz.
- **Ayrıca:** Final brieflerinden biri ham banka malzemesi olacak (mail, politika parçası, onu değiştiren bir not, kod listesi). Extractor bunu da okuyabilmeli.
- **Çözüm:** T-006. Spec'i bir LLM brief'ten çıkarsın. Resmi komut `--spec` olmadan çok adımlı ajanı kursun.

### R-2. Final test koşullarında ölçüm yapılmadı

- **Durum:** Pratik müşterileri `--reps 3` ile ve konuşma tarzlarıyla (`--style pieces|corrects|talkative|asks_back|in_words`) hiç koşmadık.
- **README kuralı:** Finalde her müşteri 3 kez test edilir ve 3'ünün de geçmesi gerekir. Final müşterileri insan gibi konuşur.
- **Çözüm:** Chat testleri geçtikten sonra, onayla, simülasyonları `--reps 3` ve her tarzla koş.

### R-3. Trace'te model çağrıları yok

- **Durum:** Builder şu an hiç model çağırmıyor. Bu yüzden trace'te `model_calls: none` yazıyor.
- **README kuralı:** Trace her model çağrısını göstermeli: model adı ve bir satırlık amaç.
- **Çözüm:** T-006'daki her LLM çağrısı `TraceWriter.add_model_call` ile trace'e yazılsın. Altyapı hazır.

## Doküman bulguları (`docs/`)

### D-1. Tool'suz adımlarda "tool çağırma" cümlesi yok

- **Yer:** `opening`, `negotiate`, `special_already_paid`, `special_dispute`.
- **Kural (`workflow-format.md`, "Rules for task_message"):** Tool'suz bir adımın prompt'u bu turda tool çağrısına izin olmadığını açıkça söylemeli. Adımın `loop_prompt`'u varsa aynı cümle orada da olmalı.
- **Çözüm:** Tool'suz her konuşma adımına bu cümleyi koddan ekle.

### D-2. Prompt tool'u adıyla anmıyor

- **Yer:** `third_party` (`schedule_callback` hiç geçmiyor), `confirm_record` (`create_promise` yerine "the promise tool" diyor).
- **Kural (`workflow-format.md`):** Adımda tool varsa prompt onu adıyla anmalı ve ne zaman çağrılacağını söylemeli.
- **Çözüm:** Adımdaki tool adlarını ve çağırma koşullarını prompt'a koddan yaz.

### D-3. "Her tool sonucundan sonra konuş" kuralı prompt'ta yok

- **Yer:** `third_party`, `confirm_record` (`identity`'de var).
- **Kural (`tools-and-code.md`, "Tool results and the next turn"):** Post-hook'a ek olarak adımın prompt'u da şunu söylemeli: her tool sonucundan sonra müşteriyle konuş ya da sıradaki tool'u çağır, bir turu asla boş bitirme.
- **Risk:** Ajan tool'dan sonra susar, müşteri telefonu kapatır.
- **Çözüm:** Tool'lu her adıma bu cümleyi ekle.

### D-4. `special_human` kimlik kontrolünü kesebiliyor

- **Yer:** `special_human` global düğümünün `excluded_nodes` listesinde `identity` yok. Diğer iki özel durumda var.
- **Kural (`workflow-format.md`, "Global nodes"):** Kesintinin zarar verebileceği adımları, örneğin kimlik kontrolünü, hariç tut.
- **Karar gerekiyor:** "İnsanla konuşmak istiyorum" isteği kimlik kontrolü sırasında da gelebilir. Bu düğüm bilerek mi açık bırakıldı? Bilerek değilse `identity` hariç tutulmalı.

## Uyan noktalar (kısa)

- **Workflow genel yapısı:** `agent_config` ve `context_variables` yok, hiçbir yerde `null` yok. AND koşulları her zaman OR grubunun içinde. Boolean karşılaştırmalar iki yazımla da yapılıyor (`"true"` ve `"True"`).
- **Düğüm türleri:** `tools` sadece konuşma düğümlerinde, `pre_actions` sadece code düğümlerinde. Passthrough düğümleri `always` geçişiyle bitiyor ve default hedefleri var. İlk adım bir konuşma düğümü, code düğümü değil.
- **Bitiş düğümleri:** `on_enter` sessiz, `disable_inactivity_monitor` açık, geçişleri boş.
- **Tur sınırı:** Her konuşma düğümünde `max_node_turns` ile birlikte `max_turn_transition` var.
- **Extraction:** Her değişkende `min_confidence` var.
- **Tool'lar:** `default` kullanılıyor, `const` hiç yok. Body alanları `body.properties` altında. Veri yazan tool'larda `maxRetries` 0. Her tool'da `try` ile korunan bir post-hook var; header'ı siliyor ve `what_to_do_next` ekliyor.
- **Mapping ve kod:** Mapping yolları `data.` ile başlıyor. Kodda `{{` ya da `}}` yok.
- **Global düğümler:** Bitiş düğümlerinin hepsi hariç tutulmuş.
- **Freya ve teslim:** `builder/freya.py` kitteki dosyanın aynısı. Güncellemeden sonra publish yapılıyor ve kontrol ediliyor. Tek slot yerinde güncelleniyor. Workflow `export_workflow` ile dışa aktarılıyor. Her çalışmada trace yazılıyor.

## Sonraki adım

- D-1, D-2 ve D-3 genel prompt düzeltmeleri. Küçük bir görevle `builder/prompts.py` ve `builder/workflow.py` içinde çözülebilirler.
- D-4 için bir karar gerekiyor.
- R-1 ve R-3 T-006'nın kapsamında.
- R-2 chat testlerinden sonra, onayla yapılacak.
