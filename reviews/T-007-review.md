# T-007 review (builder self-test: selftest.py, freya_chat.py, build.py)

Rapor: tasks/T-007-report.md. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 168 test geçiyor. Kapsam: `builder/selftest.py`, `builder/freya_chat.py`, `builder/build.py`'deki self-test değişiklikleri, `tests/test_selftest.py`.

## Karar: merge edilebilir (bir yüksek belirsizlikle)
Altyapı doğru: kit dosyası değişmemiş, vakalar spec'ten, 5xx'te kayda bakılıyor, biten çağrıya mesaj gitmiyor, bütçe bağlayıcı, trace satırları var, başarısızlık build'i engellemiyor, `--print`/`--validate`'te çalışmıyor. Ama ilk iki vaka sentetik bir `customer_id` ile banka sahte-müşterisine dayanıyor; canlıda büyük ihtimalle yanlış "fail" üretirler (bulgu 1). Build'i bozmaz, yalnızca trace'te gürültü/yanlış negatif olur; ilk onaylı canlı koşuda doğrulanmalı.

## Bulgular

### 1. [Orta-Yüksek, TO-CONFIRM] Vaka 1 ve 2 uydurma müşteriyle banka işlemlerini bekliyor
- `generate_cases` müşteri değişkenlerini `customer_id = "self-test-<vaka>"` ve sabit adlarla kuruyor (`_variables`). Banka sahte servisinde gerçek müşteri kaydı yalnızca kit'in `/v1/practice/sessions` çağrısıyla (pratik vakası kimliğiyle) oluşuyor (`run_cases.py`); self-test o dosyayı bilerek kullanmıyor. Yani `verify_identity`, `get_account` bu kimlikle bilinmeyen müşteri görür.
- Vaka 1 (`identity_to_account`) `verify_identity` **ve** `get_account` çağrısını, `account` düğümüne girişi bekliyor; kimlik doğrulanmadan `account` düğümüne geçilmez. Vaka 2 (`identity_exhausted`) dört yanlış cevapla `end_call` ve tek `close_call` bekliyor; sayaç (`wrong_answers_left`) bilinmeyen müşteride azalmayabilir. Ayrıca vaka metni "My answer to 'Ask for ...' is self-test-answer-1" biçiminde; doğum tarihi gibi biçimli bir alan için agent aracı çağırmak yerine biçimi yeniden isteyebilir.
- Yani iki vaka büyük olasılıkla `fail` (veya `missing tool(s)`) verir ve gerçek bir hata bulmadan trace'te başarısızlık görünür. Üçüncü vaka (`third_party_close`) banka kaydı gerektirmiyor, çalışır.
- **Öneri:** (a) ilk onaylı canlı koşuda bu iki vakanın ne döndürdüğünü gözleyin (bilinmeyen müşteri için `verify_identity` yanıtı, sayaç davranışı); (b) beklenti gerçekten banka kaydı gerektiriyorsa vakaları zayıflatın: vaka 1 yalnızca `opening → identity` geçişini ve `verify_identity` **çağrısının denendiğini** doğrulasın, `account` düğümünü ve `get_account`'u beklemesin; vaka 2 yalnızca hata dönen bir doğrulamada agentın dürüst kaldığını ve yanlış başarı iddia etmediğini (kapanış zorunlu değil) kontrol etsin. Bunu kod değişikliği olarak sonraki işe alın; ilk canlı gözlem hangisinin gerektiğini söyler.

### 2. [Düşük] İlk turda 5xx: çağrı kimliği yoksa yeniden gönderme çift çağrı açabilir
- Çağrı kaydını kontrol etme (F-023) yalnızca `call_id` varsa yapılıyor (`if call_id:`). İlk mesajda (henüz `callId` yok) 5xx gelirse sunucu tur işlenmiş olabilir; kod mesajı yeniden gönderiyor (en fazla 2 kez) ve her başarısız denemede arkada yetim çağrılar kalabilir. İşlenmiş turun tekrar gönderilmemesi ilkesi (F-023) ilk tur için sağlanamıyor. Etkisi küçük (bütçe içinde, ledger kullanılmıyor), ama trace'te aynı vakada birden çok çağrı olabilir. Not edin; çözüm gerekmez (kimliği öğrenmenin başka yolu yok).

### 3. [Düşük] `_is_5xx` yalnızca HTTP hata biçimini tanıyor
- Regex `-> 5xx` ve `status[=: ]5xx` arıyor (kit `api` hata biçimi ile uyumlu). `urllib` zaman aşımı ve bağlantı kopması 5xx sayılmıyor ve vakayı doğrudan `platform_error` yapıyor; kayıt kontrolü yapılmıyor. Çift gönderim riskini önlediği için güvenli yön; yalnızca geçici ağ aksaması bir vakayı gereksiz yere düşürür.

## Doğrulananlar

| Kontrol | Sonuç |
|---|---|
| `freya.py` kitle birebir | **Evet.** `cmp builder/freya.py build-the-builder-v2/freya.py` aynı, `git diff builder/freya.py` boş. Chat/get_call/end_chat için ayrı `freya_chat.py` (kit `URL`/`HEADERS`'ı yeniden kullanıyor, kit `api` ile aynı hata biçimi ve zarf açma). |
| Vakalar yalnızca spec'ten | **Evet.** `generate_cases(spec, openapi)` pratik dosyasını okumuyor; metinler spec'in soru metinlerinden ve yönlendirme değerlerinden (`identity_values[0]`, `third_party_values[0]`, `close_values[0]`) kuruluyor. Brief değeri yok: yalnızca kit çağrı değişkenleri (`customer_id`, `first_name`, `last_name`, `title`, `now`), iskelet düğüm adları ve kit sabit araç adları. (Taradım.) Not: `now` değeri sabit bir ISO tarih (`2030-01-07T12:00:00Z`); farklı `now` kullanımı gizli brief'te sorun çıkarmaz. |
| 5xx'te önce kayda bakıyor, işlenmiş turu tekrar göndermiyor | **Evet** (çağrı kimliği varsa, bkz. bulgu 2). `get_call` ile kullanıcı mesajının yeni bir `messageId` ile kayıtta olup olmadığı bakılıyor; varsa tekrar gönderilmeden devam ediliyor (F-023). İşlenmemişse en fazla 2 yeniden deneme, sonra `platform_error`. Testli (işlenmiş/işlenmemiş/tükenmiş). |
| Çağrı bitince mesaj göndermiyor | **Evet.** Her turdan sonra kayıt okunuyor; `endedReason`, `node_enter end_call` ya da `function_call_start end_call` görülünce döngü duruyor (F-031'deki ikinci `close_call` riski oluşmaz). `end_chat` yalnızca bitmemiş çağrılara, doğrulamadan **sonra** (kapanış eksikliğini gizlemesin diye) gönderiliyor. |
| 6 dk bütçe bağlayıcı | **Evet.** Tek `deadline` tüm vakalar için; her istek `min(120, kalan)` zaman aşımıyla gidiyor; her mesaj öncesi ve her vaka öncesi bütçe kontrolü var; bütçe bitince kalan vakalar `platform_error`. Son `get_call` ve `end_chat` da kalan süreyle sınırlı. (`urlopen` zaman aşımı soket işlemi başınadır; yavaş damlayan bir yanıt teorik olarak aşabilir, pratik risk düşük.) Testli. |
| Trace satırları | `self_test: case=… result=pass|fail|platform_error reason=… call_id=… seconds=…` her vaka için; `self_test_summary: total=… pass=… fail=… platform_error=…`; atlanma durumları `skipped=no_spec` / `skipped=--no-self-test`; başlangıçta `self_tests` satırı modu söylüyor. Yarışma kuralının "builder'ın kendi ajanında yaptığı test ve sonucu" şartını karşılıyor. |
| Başarısızlıkta export | **Evet.** `export` satırı ve dosya self-test'ten **önce** yazılıyor; self-test başarısız veya istisna verse bile (`except Exception` → `self_test_summary: platform_error=…`) build başarılı kalıyor, çıkış kodu değişmiyor. |
| `--print` / `--validate` | **Çalışmıyor.** Self-test yalnızca kaydet-yayımla dalında, `spec is not None` ve `--no-self-test` yokken çalışıyor; `--print`/`--validate`'te trace `not run in --print/--validate mode` yazıyor. `--single-step` (spec yok) atlanıyor. |

## Kurallara uyum
Freya isteği yok (testler sahte istemciyle), stdlib, Python 3.10+. Kit dosyası dokunulmamış. Self-test yalnızca onaylı canlı build'de çalışır (varsayılan açık; `--no-self-test` geliştirme içindir).

## İlk onaylı canlı build'de bakılacaklar
1. Vaka 1 ve 2 sonuçları (bulgu 1): `fail` ise `reason` ne diyor, `verify_identity` bilinmeyen müşteri için ne döndürdü, `wrong_answers_left` azalıyor mu.
2. Vaka 3 geçmeli; `close_call` sayısı tam 1.
3. Toplam süre 6 dakikanın altında; build toplamı 30 dakikanın altında.
4. Hiçbir vakada biten çağrıya ek mesaj gitmediği (kayıt: `call_id` başına mesaj sayısı).
