# T-005c review (F-012 end-of-call kapanış, F-005 slot kontrolü)

Rapor: tasks/T-005c-report.md. Kod değiştirmedim, Freya'ya istek atmadım. 93 test geçiyor. `builder/freya.py` kit kopyasıyla birebir aynı (`cmp`: aynı).

## Özet karar
- **F-005 (`builder/slots.py`): merge edilebilir.**
- **F-012 (`close_call_on_hangup`): merge edilebilir, ama koşullu.** Çift kayıt koruması kodda doğru; ancak korumanın çalışması kit'te belgelenmemiş iki davranışa bağlı. İlk onaylı chat/voice testinde **normal kapanan çağrıda ledger'da tek `close_call`** görülmeden submission'a alınmamalı (aşağıda Bulgu 1).

## F-012 bulguları

### 1. [Orta-Yüksek, TO-CONFIRM] Koruma "açık kalıyor": hook çalışmazsa veya değişkenler görünmezse her çağrıda ikinci `close_call` gider
- `workflow.py` `_hangup_hook_code`: atlama kararı `close_call_ok`/`close_attempts` değişkenlerine ve pre-hook'un çalışmasına bağlı. Araç gövdesi varsayılan olarak gerçek URL'yi ve `default` outcome'u taşıyor. İki durumda atlama olmaz ve normal kapanan her çağrı ikinci kez `close_call` yapar:
  - (a) `end_of_call` araçlarında `pre_process_code` çalışmıyorsa (kit `tools-and-code.md` "Lifecycle tools" bölümü pre-hook'tan söz etmiyor; "malformed lifecycle tool is dropped without an error" der);
  - (b) çağrı bittikten sonra çalışan araç `vars`'ta `close_call_ok`/`close_attempts` değerlerini görmüyorsa (kit yalnızca `{{call.*}}` değişkenlerini garanti ediyor; `response_mapping` bu araç için uygulanmıyor, ama node değişkenleri için bir şey söylenmiyor).
- Brief "tam olarak bir close_call" der; çift kayıt, eksik kayıttan kötü (rapor da böyle yorumluyor). 
- **Düzeltme (a) için, küçük ve güvenli:** gövdeyi/URL'yi fail-closed yap. Araç varsayılanında `url` boş olsun; hook yalnızca "gönder" dalında gerçek URL'yi `config['url']`'e yazsın. Hook çalışmazsa istek gitmez (çift kayıt yok, en kötü ihtimalle hang-up kaydı kaybolur). (b) için kod çözümü yok; bu **ilk onaylı testte** doğrulanacak: PUB-03 benzeri normal kapanışta ledger'da tek `close_call`, `hangup_close` değişkeni `skipped` (trace/variable dump'ta).
- Karar: Bulgu 1 çözülmeden **submission yok**; chat testinde kanıt gerekli.

### 2. [Orta, TO-CONFIRM] URL boşaltma seçeneğinin riski
- `config['url'] = ''` ve `config['body'] = {}` (workflow.py ~655). Kit'te boş URL davranışı belgesiz; raporun gözlemi "URL is required" hatası. Riskler: (i) başarısız lifecycle çağrısı iz bırakıyor mu (ledger'a yazılmaz, istek gitmiyor), (ii) `maxRetries 0` olduğu için tekrar yok (iyi), (iii) judge'ın gördüğü trace'te "tool failed" görünüp honesty puanını etkiler mi (araç çağrı bittikten sonra çalışıyor, müşteriye bir şey söylenmiyor; olasılık düşük ama doğrulanmalı), (iv) engine boş URL'yi "varsayılan URL" ile doldurup yine göndermesin: ilk testte gözlem şart.
- Yedek: rapor (b) gövde boşaltma ve (c) hata atma seçeneklerini doğru elemiş. Tek ek öneri Bulgu 1'deki fail-closed tasarım; o zaman URL boşaltmaya gerek kalmaz, "gönderme" varsayılan olur.

### 3. [Düşük] `close_attempts > 0` ise hang-up de göndermiyor
- Kapanış zinciri iki denemede başarısızsa kayıt hiç yok. Çift kayıt riskine karşı bilinçli seçim (rapor açık soru 1); kabul. Tek ek not: `close_attempt` sayacı `close_record` istek **öncesi** artıyor (`workflow.py` ~979), yani müşteri tam o iki adım arasında kapatırsa sayaç >0 ve istek hiç gönderilmemiş olabilir; çok dar pencere (code → engine api arası), kabul edilebilir.

### 4. [Bilgi] Doğrulanmış müşteri kapatınca outcome `default` satırından geliyor
- A fixture'ında `hangup` eşlenmemiş, `default` = `no_promise/refused`. Brief hang-up için satır tanımlamıyor; T-006 extractor'ı brief'te karşılık bulamazsa trace'e varsayılanı yazmalı (rapor açık soru 2). Yanlış outcome da puan kaybettirir, ama kayıtsızdan iyidir.

## İstenen kontroller

| Kontrol | Sonuç |
|---|---|
| Hang-up aracı çift kayıt yapmaz mı | Kodda yapmaz: `close_call_ok == true` veya `close_attempts > 0` → URL/gövde boş, `hangup_close = skipped`. Testler 1, 2 ve ok=true için doğruluyor. Çalışma zamanı garantisi Bulgu 1'e bağlı. |
| URL boşaltma riski | Bulgu 2. |
| Outcome seçimi kapanış zinciriyle aynı mı | Evet. `_outcome_choice_code` (TABLE + `choose()`) ortak, `closing` adımı da aynı parçayı kullanıyor. `wins_over_promise` ve "kayıtlı söz varsa `promise`" kuralı aynı. Fark yalnızca aday sırası: son `close_state`, sonra `hangup_unverified` (kimlik doğrulanmamışsa), sonra `hangup`, sonra `default`. `close_state` dolu ise (kapanış başlamış) kapanış zinciriyle aynı sonucu verir. |
| Hardcode | Yok. `hangup`/`hangup_unverified` iskelet durum adları (`spec.py` `HANGUP_CLOSE_STATES`), brief değeri değil; `outcome`/`reason` alan adları spec'ten (`closing.data`), değerler spec'in outcome tablosundan. |
| Kit uyumu | Üst seviye `tools`, `config.alwaysRunsAt: ["end_of_call"]`, `maxRetries 0`. Her gövde alanı model olmadan çözülüyor (model çağrısı tetiklenmez); modelin dolduracağı alanlar şemadan çıkarılmış; `response_mapping` kaldırılmış (kit: end_of_call'da uygulanmıyor). `customer_id: {{customer_id}}` çağrı değişkeni. Açıklama metni modele gösterilmeyen araçta "CALL this tool..." ifadesini taşıyor; zararsız, istenirse kısaltılabilir. |

## F-005 (`builder/slots.py`)
- `freya.py` değişmedi; `save_with_slot_check(client, slot, ...)` `freya` modülünü `client` olarak alıyor (`api`, `workspace_id`, `save_workflow` modül düzeyinde mevcut).
- Akış doğru: kayıtlı ID varsa önce `GET /api/v2/workflow/{id}`; yalnızca `-> 404` ise kaydı siler ve trace'e uyarı yazar; 500/ağ hatası yükselir (yanlışlıkla yeni workflow açılmaz, workspace sınırı korunur); bozuk slot dosyası uyarıyla sıfırlanır; diğer slotlar korunur. 5 test bunları doğruluyor.
- Düşük notlar: 404 tespiti metin eşleşmesine (`"-> 404"`) dayanıyor, `freya.api` hata biçimine bağlı (F-005 gözlemiyle uyumlu, kit değişirse kırılır; hata nesnesinde kod varsa onu kullan). Kontrol `validate_workflow`'dan sonra yapılıyor; dry-run eski ID'yi kullanmıyorsa sorun değil. `build.py` içe aktarması paket/script iki yolda da var.

## Kurallara uyum
Freya isteği yok, testler çevrimdışı (sahte client), stdlib, Python 3.10+. Prompt metni değişmemiş.

## İlk onaylı testte bakılacaklar (TO-CONFIRM, rapordaki listeye ek)
1. Normal kapanışta ledger'da tek `close_call` (önce bu).
2. `hangup_close` değişkeni: `skipped` (normal) / `sent:<durum>` (erken kapatma).
3. Boş URL'nin hata mı, sessiz atlama mı olduğu ve honesty judge'ına etkisi.
4. Pre-hook'un `config['body']` düzeltmesinin isteğe yansıması (T-005b'deki hook varsayımıyla aynı).

## Karar: merge edilebilir
F-005 ve F-012 kodu kurala uygun ve testli. F-012 için Bulgu 1'in fail-closed düzeltmesi (varsayılan boş URL, hook yalnızca gönderirken gerçek URL'yi yazar) tavsiye ediliyor ve küçük bir iş; çalışma zamanı kanıtı (tek `close_call`) gelmeden submission'a alınmamalı.
