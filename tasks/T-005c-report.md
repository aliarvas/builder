# T-005c raporu: son açık kod bulguları (F-012, F-005)

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

İki bulgu da kodda kapandı. `python3 -m unittest` 93 testin hepsini geçiyor (T-005b-fix Fix 2 sonrası 85). `--print --spec tests/fixtures/spec-brief-a.json` çalışıyor. Sızıntı testi yeşil. Prompt metni değişmedi; `docs/PROMPTS.md` yeniden üretildi, fark yok. Freya'ya istek yok, commit yok, `env.sh` okunmadı, `builder/` içine brief değeri girmedi. Çalışma bir bağlantı kopmasıyla bölündü; kaldığı yerden tamamlandı.

Değişen dosyalar:

- **Kod:** `builder/workflow.py`, `builder/spec.py`, `builder/build.py` ve yeni `builder/slots.py`.
- **Test ve fixture:** `tests/test_multi_step.py`, yeni `tests/test_slots.py`, `tests/fixtures/spec-brief-a.json`.
- **Doküman:** `docs/UAT-FINDINGS.md`.

## 1. F-012: müşteri kapatınca kayıt yok

### Ne yapıldı

- **Lifecycle aracı:** workflow'un üst seviye `tools` listesine bir end-of-call aracı eklendi (`close_call_on_hangup`).
  - `config.alwaysRunsAt: ["end_of_call"]` ve `maxRetries: 0` (yazma aracı).
  - Aynı `close_call` endpoint'ine gidiyor ama adı farklı. Böylece kapanış zincirindeki `close_call` sayaçları ve `_args`/`_response` değişkenleri karışmıyor.
- **Model çağrısı yok:** kit'e göre end-of-call aracında çözülemeyen bir `{{var}}` kalırsa parametreleri bir model çağrısı dolduruyor. Bu yüzden her gövde alanı model olmadan çözülüyor:
  - `customer_id` → `{{customer_id}}` (çağrı değişkeni);
  - `outcome` / `reason` → spec'in `default` satırının **sabit** değerleri (reason boşsa alan hiç yok);
  - modelin dolduracağı diğer alanlar şemadan çıkarıldı; `required` yok.
- **Gerçek outcome'u pre-hook hesaplıyor.** Kapanış zinciriyle aynı kod ve aynı outcome tablosu kullanılıyor: tablo ve `choose()` ortak bir parçaya (`_outcome_choice_code`) ayrıldı, `closing` adımı da artık onu kullanıyor. Aday durumlar sırayla:
  1. son `close_state` (kapanış başlamışsa);
  2. kimlik doğrulanmadıysa `hangup_unverified`;
  3. `hangup`;
  4. hiçbiri eşleşmezse `default` satırı.
  Ardından kapanış zincirindeki kural aynen uygulanıyor: kayıtlı söz varsa ve seçilen satırda `wins_over_promise` yoksa `promise` seçiliyor.
- **Spec:** `HANGUP_CLOSE_STATES = ("hangup", "hangup_unverified")` isteğe bağlı bitiş durumu olarak `OPTIONAL_CLOSE_STATES` / `CLOSE_STATE_NAMES`'e eklendi. Fixture A'da `hangup_unverified` → `not_verified/declined` (Brief A kural 45'e göre); `hangup` eşlenmedi, `default` satırına düşüyor.

### Çift kayıt önlemi

- Pre-hook, kapanış zinciri `close_call`'ı zaten göndermişse (`close_call_ok` true **veya** `close_attempts > 0`) isteği etkisizleştiriyor: `config['url'] = ''`, `config['body'] = {}`, `vars['hangup_close'] = 'skipped'`.
- Zincir bir deneme yapıp başarısız olduysa da gönderilmiyor. Görevdeki ilke izlendi: brief "tam olarak bir close_call" dediği için çift kayıt, eksik kayıttan daha kötü.
- **Neden URL boşaltma:** kit dokümanında lifecycle aracını atlamanın bir yolu yok. Pre-hook yalnızca isteği yeniden yazabiliyor. Seçenekler:
  - (a) URL'yi boşaltmak: istek bankaya hiç ulaşmaz. Kit'te "URL is required" hatası görülmüş. **Seçilen bu.**
  - (b) Gövdeyi boşaltmak: banka `ok:false` döner ama ledger'da bir çağrı izi kalabilir.
  - (c) Pre-hook'ta hata atmak: davranış belgesiz; kod kuralı (asla hata atma) ile de çelişiyor.

### Testler

- **Biçim:** üç fixture'da araç üst seviyede ve tek; `end_of_call`; `maxRetries 0`; zorunlu alan yok; her alanın varsayılanı sabit veya çağrı değişkeni. Pre-hook derleniyor, `{{`/`}}` içermiyor.
- **Atlama:** `close_call_ok` true, `close_attempts` 1 ve 2 → URL boş, gövde boş.
- **Outcome:**
  - kimlik doğrulanmadan kapatma → `not_verified/declined`;
  - doğrulandı, söz yok → `default` (`no_promise/refused`);
  - kayıtlı söz → `promise` (reason yok);
  - kapanış başlamış `special:human` → `transferred/human`;
  - `close_state = identity_failed` → `not_verified/failed`;
  - fixture B'de hang-up satırı yok → `default`.
- **Bozuk girdi:** hata atmıyor.

## 2. F-005: silinmiş workflow için eski slot

- Yeni `builder/slots.py` içinde `save_with_slot_check(client, slot, workflow, warn=...)`. `freya.py` (kit kopyası) değişmedi.
- **Akış:**
  1. Slot dosyasında bu slot için bir workflow ID varsa önce mevcut `freya.api` ile `GET /api/v2/workflow/{id}` okunuyor.
  2. **404** dönerse eski kayıt slot dosyasından siliniyor, trace'e `warning: stored workflow <id> for slot '<slot>' no longer exists; creating a new workflow` yazılıyor ve `freya.save_workflow` yeni bir workflow oluşturuyor.
  3. **404 dışındaki** hatalar (500, ağ) build'i durduruyor. Geçici bir hata yüzünden yeni workflow açılmasın (workspace sınırı).
  4. Slot dosyası okunamıyorsa uyarıyla sıfırlanıyor.
- `build.py` kaydetme adımında `freya.save_workflow` yerine bu fonksiyonu çağırıyor; uyarılar trace'e gidiyor.
- **Testler** (`tests/test_slots.py`, sahte client):
  - kayıtlı ID yok → oluşturma yolu ve tek uyarı; diğer slotlar korunuyor;
  - ID var → okuma ve güncelleme yolu, uyarı yok;
  - slot yok → kontrolsüz oluşturma;
  - 500 → hata yükseliyor;
  - bozuk slot dosyası → uyarıyla oluşturma.

## TO-CONFIRM (onaylı test)

1. **Tetiklenme:** üst seviye end-of-call aracı müşteri kapattığında (chat'te müşteri tarafı bitirince ve simülasyonda) tetikleniyor mu?
2. **Değişkenler:** pre-hook o anda çağrının değişken tablosunu (`close_call_ok`, `close_attempts`, `close_state`, `identity_verified`, `promise_recorded_count`) görüyor mu?
3. **Normal kapanış:** URL boşaltılınca hiçbir istek gitmiyor ve çağrı hatasız bitiyor mu? Normal kapanan bir çağrıda (PUB-03 gibi) ledger'da **tek** `close_call` kalmalı. İlk bakılacak şey bu.
4. **Hang-up kaydı:** müşteri ortada kapatınca (PUB-07 benzeri) ledger'da hesaplanan outcome görünüyor mu?
5. **Pre-hook düzeltmesi:** `config['body']`'de düzeltilen `outcome`/`reason` değerleri isteğe gerçekten yansıyor mu? T-005b'deki hook varsayımıyla aynı.
6. **404 metni:** silinmiş workflow okunduğunda `freya.api` hatası `-> 404` içeriyor mu? F-005'teki gözleme göre evet ("Workflow not found").

## Açık sorular

1. **Çift kayıt mı, eksik kayıt mı?** Kapanış zinciri iki denemede de başarısız olursa hang-up aracı da göndermiyor; çağrı kayıtsız bitebilir. Çift kayıt riskini almamak için bilinçli bir seçim. CTO tersini isterse tek satırlık değişiklik: `close_attempts > 0` yerine yalnızca `close_call_ok` kontrolü.
2. **Doğrulanmış kapatmanın outcome'u:** brief'ler hang-up için bir satır tanımlamıyor. Doğrulanmış müşteri kapatınca fixture A'da `default` (`no_promise/refused`) yazılıyor. T-006 extractor brief'te bir karşılık bulursa `hangup` / `hangup_unverified` satırlarını doldurmalı, bulamazsa trace'e varsayılanı yazmalı.
3. **Üçüncü kişi kapatırsa:** üçüncü kişi telefonu kapatırsa durum `hangup_unverified` sayılıyor (kimlik doğrulanmamış). Ayrı bir `third_party` hang-up durumu istenirse eklenebilir.

## Fix (review T-005c Bulgu 1: fail-closed)

- **URL varsayılanı boş:** `close_call_on_hangup` aracının `url` varsayılanı artık boş. Gerçek URL yalnızca pre-hook'un içinde. Hook bunu `config['url']`'e **yalnızca gönder dalında** ve en son adımda yazıyor: outcome/reason gövdeye yazıldıktan sonra.
- **Gitmeyen durumlar:** hook hiç çalışmazsa, gönderme kararından önce hata atarsa, gövde sözlük değilse (`hangup_close = skipped:no_body`) veya atlama dalına girerse istek gitmez. En kötü ihtimalle hang-up kaydı kaybolur; çift kayıt olmaz.
- **Build kontrolü:** `close_call`'ın sabit bir URL'si yoksa build açık bir SpecError ile duruyor.
- **Testler:** 94'ün hepsi geçiyor (öncesi 93).
  - araç varsayılanı boş URL;
  - hook çalışmazsa URL boş kalıyor;
  - gönder dalı gerçek URL'yi (`close_record`'daki ile aynı) yazıyor;
  - gövde `None` iken URL boş kalıyor;
  - mevcut outcome testleri gerçek URL'yi doğruluyor.
- **TO-CONFIRM (değişmedi):** normal kapanan çağrıda ledger'da tek `close_call` ve `hangup_close = skipped`; müşteri kapatınca hesaplanan outcome'un ledger'a düşmesi. Review'a göre bu kanıt olmadan submission yok.

Freya'ya istek yok, commit yok, `env.sh` okunmadı.
