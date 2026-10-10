# T-005a-fix raporu: review bulguları 1, 2, 4, 5, 6, 7

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10 · **Kaynak:** `reviews/T-005a-review.md` "Bulgular"

## Özet

İstenen altı bulgu düzeltildi. Bulgu 3'e dokunulmadı; o chat testinde doğrulanacak. `python3 -m unittest` 62 testin hepsini geçiyor (öncesi 60). `--print --spec tests/fixtures/spec-brief-a.json` çalışıyor (36 adım, en büyük prompt identity, yaklaşık 506 token). `docs/PROMPTS.md` yeniden üretildi. Freya'ya istek yok, commit yok, `env.sh` okunmadı.

Değişen dosyalar: `builder/spec.py`, `builder/workflow.py`, `builder/prompts.py`, `docs/PROMPTS.md`, `tests/test_multi_step.py`, `tests/fixtures/spec-*.json` (üçü de).

## Bulgu başına değişiklik

### 1. Kayıtlı söz varken kapanış sonucunun önceliği

- **Spec:** outcome satırlarına isteğe bağlı `wins_over_promise` alanı eklendi (varsayılan `false`). Değer `true`/`false` değilse spec yüklenmiyor.
- **Kapanış kodu:** önce durumun kendi satırı seçiliyor (satırı yoksa `default`). En az bir söz kaydedilmişse ve seçilen satırda `wins_over_promise` yoksa `promise_recorded` satırı kullanılıyor. Özel yollar, kendi outcome/reason çiftlerinin satırındaki bayrağı kullanıyor.
- **Fixture'lar:** `transferred` satırlarına (A, B) ve synthetic'teki `escalated` satırına `wins_over_promise: true` eklendi. Bu, "kayıttan sonra transfer olursa transferred" kuralını karşılıyor.
- **Sonuç:** Brief B'de bir ürün kaydedilip diğeri iki kez başarısız olursa outcome artık `promise`. Eskiden `no_promise/service_error` oluyordu.
- **Test:** üç fixture'da her durum, 1 kayıtlı sözle denendi; B'de `promise_failed` + 1 kayıt → `promise`; A'da `special:human` + 1 kayıt → `transferred/human`.

### 2. `close_call` için `maxRetries`

`close_call` artık araç seviyesinde `maxRetries: 0` (yazma aracı kuralı). Tekrar deneme yalnızca akıştaki `close_attempt` döngüsünde ve en fazla 2 çağrı. Test bunu doğruluyor.

### 4. Değişken adı

Kapanış cümlesinin değişkeni `closing_say` yerine artık `closing_sentence`; düğüm adı `closing_say` olarak kaldı. Sabit satır `{{closing_sentence}}` okuyor.

### 5. Son kimlik sorusundan sonra

Kimlik şablonuna yeni kural eklendi: son soru doğrulandığında başka soru sorulmaz. Ajan cevapların eşleştiğini söyler ve henüz hesap bilgisi vermez. Bu, F-021 gecikmesi sürerse ajanın uydurma bir soru sormasını önler.

### 6. Sızıntı testindeki izin listesi

`spec.py` artık iskeletin sabit bitiş-durumu adlarını tek bir yerde (`CLOSE_STATE_NAMES`) dışa veriyor. Test listeyi elle yazmıyor, buradan türetiyor. Dosya bazlı kapsam (öneri) yapılmadı; aşağıdaki açık sorulara bakın.

### 7. Fixture A'da `turn_limit`

`turn_limit` artık `no_promise/service_error` satırında değil, `default` satırına düşüyor (A'da `no_promise/refused`). Aynı düzeltme B'ye de uygulandı. `service_error` yalnızca gerçek hata durumlarında kaldı (`promise_failed`, `account_failed`). Test bunu A için doğruluyor.

## Dokunulmayan

- **Bulgu 3 (TO-CONFIRM, chat testi):**
  - sabit cümle chat'te söyleniyor mu, `close_call`'dan önce mi görünüyor;
  - `close_reason` boşken `reason` alanı düşüyor mu;
  - `close_record` `data.ok`'u dolduruyor mu.

## Açık sorular

1. **Brief B kural 11:** `add_note(service_error)` hâlâ yok. Kaydedilen sözler artık outcome'da korunuyor, ama not yazılmıyor. T-005 kapsamında.
2. **Sızıntı testinde dosya bazlı kapsam:** testte `failed`, `default`, `return` gibi genel sözcükler hâlâ her dosyada izinli. Dosya bazlı kapsam istenirse ayrı küçük bir iş olur.
3. **T-006 için:** `wins_over_promise` ve `default` satırı seçimini artık extractor'ın brief'ten çıkarması gerekiyor. Spec formatına yeni alan eklendi.
