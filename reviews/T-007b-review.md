# T-007b review (self-test vakaları bilinmeyen müşteriye göre)

Kaynak: tasks/T-007-report.md "T-007b" bölümü, `builder/selftest.py`, `tests/test_selftest.py`. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 194 test geçiyor.

## Karar: düzeltme gerekli
Yaklaşım doğru (hiçbir vaka bankanın başarılı olmasını beklemiyor, dürüstlük odaklı), ama iki yerde canlıda yanlış sonuç verecek: üçüncü vaka kendi workflow'umuzun yeniden deneme davranışıyla çelişiyor ve her seferinde düşer (bulgu 1); dürüstlük kontrolü olay biçimi varsayımı yüzünden büyük olasılıkla hiçbir zaman devreye girmez (bulgu 2). İkisi de küçük düzeltme.

## Bulgular

### 1. [Yüksek, her seferinde yanlış FAIL] `third_party_close` tam bir `close_call` deneme bekliyor; workflow başarısızlıkta iki deneme yapıyor
- `_validate`: `close_count > 1 or (require_close and close_count != 1)` → fail. Testler bunu açıkça sabitliyor (`test_two_close_calls_fail_even_when_not_required`).
- Workflow tasarımı: `close_record` geçişleri `end_call` (başarı **veya** `close_attempts > 1`) ve aksi halde `close_attempt` → tekrar `close_record`. Üretilen düğümlerden doğruladım (kendim yazdırdım). Banka sahte müşteri için `ok=false` döndürdüğünde zincir tam **iki** kez dener (yazma araçlarında bilinçli tek yeniden deneme; OpenAPI `close_call` 500 açıklaması "the call may be repeated"). Yani canlı kayıtta iki `function_call_start close_call` olayı beklenir (kit api.md: bir `api_call` için `function_call_start` olayı yazılır); vaka 3 `close tool count was 2, expected 1` ile her seferinde düşer. Motorun çalıştırdığı `pre_actions` çağrıları olay üretmiyorsa bu kez sayı 0 olur ve yine düşer.
- **Düzeltme:** beklenti workflow'un kendi politikasından gelsin: kapanış beklenen vakada 1 ila 2 `close_call` denemesi kabul et; 2 ise ilkinin başarısız (`function_call_complete` ile `ok=false`) olduğunu doğrula; 2'den fazlası hata (F-031'in yakaladığı döngü). Sabiti (`MAX_CLOSE_ATTEMPTS = 2`) workflow tarafıyla paylaş. Olay hiç görünmezse (0) bunu "doğrulanamadı" olarak `platform_error`/uyarı yap, `fail` değil; asıl kanıt ledger yerine kayıtta `end_call` düğümü ve `close_record` düğümüne giriş olabilir. Testi bu davranışa göre güncelle (2 deneme, ilki başarısız → pass; 3 → fail).

### 2. [Orta, TO-CONFIRM] Dürüstlük kontrolü başarısız araç sonucunu tanımayabilir
- `_failed_result` yalnızca `result.get("ok") is False` bakıyor (üst düzey `ok`). Kit'in anlattığı api_call sonucu `status`, `data`, `message`, `status_code`, `header` biçiminde ve banka yanıtı `data` altında (`check_answer_response.data.ok`, `tools-and-code.md` 264–275). Bizim `post_process_code` da `result['data']`'yı düzenliyor, üst düzey `ok` eklemiyor. `function_call_complete` olayındaki `result`'ın bu zarf mı yoksa yalnızca gövde mi olduğu kit'te açık değil; gerçek bir kayıt örneği yok (aradım).
- Zarf biçimindeyse `failed` hiç `True` olmaz, `_honesty_violation` her zaman `None` döner ve iki dürüstlük vakası kontrol yapmadan PASS verir (sessiz yanlış PASS). Testler `{"ok": False}` üst düzey biçimini kullandığı için bunu görmüyor.
- **Düzeltme:** hem `result.ok` hem `result.data.ok` (ve gerekirse `result` bir JSON dizesiyse çözülmüş hâli) bakılsın; ayrıca `route_evaluated.variable_table` içindeki `<tool>_response.data.ok == "false"` ikinci kanıt olarak kullanılabilir. İlk onaylı canlı koşuda gerçek olay biçimi kaydedilip test fixture'ı yapılsın.

### 3. [Düşük] Başarı iddiası tespiti dar ve `no` sözcüğü fazla geniş
- `_SUCCESS_CLAIM` yalnızca birkaç kalıbı tanıyor ("you're verified", "identity has been verified", "thank you for verifying", "successfully recorded" ...). "Thanks, that all matches", "you passed security", "I've confirmed your details", "let me pull up your account" gibi yaratıcı iddialar kaçar. `_NEGATION` listesindeki `no` ve `until/before/once/if` cümlede varsa iddiayı iptal ediyor: "Thanks, no problem, you are verified." kaçar. Rapor bunu "duman testi, yargıç değil" diye zaten kabul ediyor; kabul. Yalnızca yanlış PASS tarafında olduğunu bilin; yanlış FAIL ihtimali düşük.
- Ek öneri: başarısız kimlik sonrası agent'ın `get_account` tarafına ait bir bilgi (borç tutarı) söylemesi daha güvenilir bir kanıt olur: vaka 2'de müşteri "ne kadar borcum var" diye soruyor; yanıtta rakam (`\d` içeren para tutarı) geçiyorsa dürüstlük ihlali sayılabilir (hesap alınmadığı için tutar uydurma demektir). Bu kontrol dile ve brief'e bağlı değil.

### 4. [Bilgi] Diğer
- Vaka 1 ve 2'nin yalnızca mesaj sonu farklı (vaka 2'de ek bir soru). Aynı arka planı iki kez kullanıyorlar; bütçe (6 dk) içinde sorun yok.
- Placeholder cevaplar ("self-test-answer-N") ile ajanın `verify_identity`'yi çağırıp çağırmayacağı hâlâ belirsiz (raporun TO-CONFIRM'i); çağırmazsa `missing tool(s): verify_identity` olur. İlk canlı koşuda gözlenecek.

## Doğrulananlar

| Kontrol | Sonuç |
|---|---|
| Vakalar bilinmeyen müşteri gerçeğine uygun mu | **Evet.** Hiçbir vaka bankanın başarılı olmasını beklemiyor. Vaka 1/2: `opening → identity`, `verify_identity` denendi, `account` düğümü ve `get_account` **yasak** (kimlik doğrulanmadan hesap alınamaz); kapanış gerekmiyor. Vaka 3: banka kaydı gerektirmeyen üçüncü kişi kapanışı. Hepsi yalnızca spec'ten üretiliyor, brief değeri yok. |
| `error` olayları | Araç hataları (`function` alanı veya araç adı geçen) tolere ediliyor, motor hataları (diğer `error`) hâlâ FAIL: banka hatası ile motor hatası ayrımı mantıklı (testli). |
| Yasak düğüm/araç | `forbidden_nodes`/`forbidden_tools` çalışıyor (testli); doğru mantık, çünkü kimlik doğrulanmadan hesap görünürse ya bir sızıntı ya yanlış yönlendirme. |
| Dürüstlük kontrolü anlamlı mı | Kavram doğru (araç başarısızsa başarı iddiası yok), deterministik, model çağrısı yok. Uygulamada bulgu 2 yüzünden devreye girmeyebilir. |
| `close_call` tam bir kez denendi | **Hayır, workflow ile çelişiyor** (bulgu 1). |

## Kurallara uyum
Pratik dosyası okunmuyor, brief değeri yok, Freya isteği yok, yalnızca `selftest.py` ve test dosyası değişmiş.

## Düzeltme sonrası
İlk onaylı canlı koşuda her vakanın `reason` alanını okuyun ve bir `function_call_complete` olayının gerçek biçimini kaydedin (fixture olarak).

---

# Fix kontrolü (bulgu 1–3; rapor: tasks/T-007-report.md "T-007b Fix")

Kod değiştirmedim, Freya ve modele istek atmadım. `python3 -m unittest`: 223 test geçiyor (claude-dev'in F-043/044 çalışması dahil değil). Kapsam: `builder/selftest.py`, `tests/test_selftest.py`.

## Karar: merge edilebilir
Üç bulgu da kapandı; iki küçük not ve ilk canlı koşuda doğrulanacak üç varsayım (aşağıda) kaldı. Kendi denemelerim: kapanış 1–2 deneme kuralı doğru, sonuç sınıflandırması dört biçimi tanıyor, başarı iddiası kalıpları önceki dar listeden belirgin geniş.

## Bulgu 1 (kapanış denemesi): kapandı
- `MAX_CLOSE_ATTEMPTS = 2`; `_close_problem` mantığı: 1–2 `close_call` gönderimi kabul, 3 ve üstü FAIL (F-031 döngüsü), yeniden deneme yalnızca önceki denemenin sonucu başarılı **değilse** geçerli ("retried after a successful attempt" FAIL), `close_call_on_hangup` zincirin gönderiminden sonra FAIL, hang-up başlangıcının `args.url` boşsa atlanmış sayılıyor (hook URL'yi boşaltıyor). Kapanış gerekli ama olay yoksa: `close_record` düğümüne girilmişse `platform_error` (olay görünmüyor), girilmemişse `fail`; `platform_error` yalnızca başka hiçbir kontrol düşmemişse bildiriliyor. Bu, benim önerimle birebir örtüşüyor.
- **Workflow ile paylaşım:** sabit `selftest.py`'de ayrıca tanımlı (workflow.py'de ortak sabit yok, geçiş koşulu `close_attempts greater_than 1` düz sayı); senkron bir testle bağlanmış (render edilen Brief A workflow'unda `close_record` eşiği `MAX_CLOSE_ATTEMPTS - 1` olmalı). Workflow değişirse test kırılır, yani kayma sessiz olmaz. Daha temizi sabiti workflow.py'de tanımlayıp iki yerden içe aktarmak; F-043/044 workflow.py'de çalışıldığı için sonraya bırakılabilir (düşük).
- Not (düşük, TO-CONFIRM): hang-up başlangıç olayının `args.url` değerinin hook çalıştıktan *sonraki* hâli mi gösterdiği bilinmiyor. Hook öncesi (dolu URL) gösteriliyorsa, zincir `close_call` göndermişken olay "gönderim" sayılır ve vaka 3 `hang-up close sent after the closing chain` ile yanlış FAIL olur; ayrıca sohbet yolunda `end_of_call` aracının hiç tetiklenip tetiklenmediği belirsiz. İlk canlı kayıtta bakın; yanlış FAIL görülürse hang-up başlangıcını `fail` yerine `WARN`/`platform_error` yapın (gerçek çift gönderim denetimi zaten ledger'dan yapılır).

## Bulgu 2 (başarısızlık tanıma): kapandı
`_tool_outcome` `function_call_complete.result`'ı üst düzeyde ve `data`/`body`/`response` içinde, JSON dizesi olsa bile okuyor. Kendim denedim:

| Sonuç biçimi | Sınıf |
|---|---|
| `{"ok": false}` | tool_failed |
| `{"status":"success","data":{"ok":false,"error":"unknown customer_id"},"status_code":200}` (kit zarfı) | tool_failed |
| `'{"data": {"ok": "false"}}'` (JSON dizesi, "false" metni) | tool_failed |
| `{"status":"success","data":{"ok":true}}` | tool_ok |
| `{"data": {}}` veya sonuç yok | tool_unknown |
| `{"status_code": 404}` | tool_failed |

Dürüstlük penceresi beklenen aracın `function_call_start`'ında açılıyor ve yalnızca tanınmış bir `ok: true` sonucuyla kapanıyor; bilinmeyen/eksik sonuç kontrolü artık sessizce kapatmıyor (önceki yanlış PASS yolu kapandı). Rapor `variable_table`'ı ikinci kanıt olarak kullanmıyor (benim isteğe bağlı önerimdi); bilinmeyen sonucun pencereyi açık tutması aynı güvenliği veriyor, kabul.

## Bulgu 3 (başarı iddiası kalıpları): kapandı, küçük bir yanlış bayrak var
Denedim (13 olumlu, 10 olumsuz cümle):
- **Yakalananlar (hepsi):** "Thanks, no problem, you are verified." (eski kod kaçırıyordu), "that all matches", "You've passed security", "I've confirmed your details", "Let me pull up your account", "Your balance is …", "You are now verified…", "identity has been successfully verified", "Thank you for verifying", "Everything checks out", "Identity confirmed", ve başarısız kimlik sonrası para tutarı ("$250", "1,200 euros").
- **Doğru şekilde bayraklanmayanlar:** "I could not verify those details. Could you repeat your answer?", "No problem, could you repeat your answer?", "Unfortunately I wasn't able to verify you, so I can't share account details.", "Once you are verified I can pull up your account.", "Your answer was not accepted, but you can try again.", "Please tell me your date of birth again.".
- **Tek yanlış bayrak (düşük):** "If the answers match, I will pull up your account." Koşul ayrı bir yan cümleye bölününce ("If the answers match" / "I will pull up your account") ikinci yan cümlede olumsuzlama/koşul sözcüğü kalmıyor ve iddia sayılıyor. Düzeltme: bir yan cümle `if/once/until/after/before` ile başlayan bir yan cümleyi hemen izliyorsa koşullu kabul et. Etkisi: nadir yanlış FAIL; vaka dürüstlük testinde bir sonuç düşerse `reason` metnine bakın.

## Doğrulanacaklar (ilk onaylı canlı koşuda)
1. `function_call_complete.result`'ın gerçek biçimi: bir kayıt fixture olarak saklansın.
2. `pre_actions` ile çalışan kapanış çağrıları `function_call_start` olayı üretiyor mu (üretmiyorsa vaka 3 `platform_error` verir, doğru davranış).
3. Hang-up başlangıç olayı (varsa) `args.url` değerini hook'tan önce mi sonra mı gösteriyor.

## Kurallara uyum
Yalnızca `selftest.py` ve testi değişmiş, brief değeri yok, Freya/model isteği yok.
