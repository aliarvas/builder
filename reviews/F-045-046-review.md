# F-045/046 ve F-049 self-test review

Kaynak: tasks/T-007-report.md "F-045/046 (and F-049)" bölümü; `builder/selftest.py`, `tests/test_selftest.py`. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 243 test geçiyor.

## Karar: merge edilebilir (bir hata notuyla)
F-045 ve F-046 düzeltmeleri doğru ve genel. F-049 durum ayrımı mantıklı, ama doğru işlenmiş bir kapanış turu 5xx'ten sonra yanlışlıkla "durum kaybı" sayılıyor (bulgu 1); sonuç yanlış `platform_error`, yanlış PASS/FAIL değil.

## Bulgu

### 1. [Orta-Düşük] İşlenmiş kapanış turu 5xx sonrası `turn_state_lost` sayılıyor
- `_turn_state`: "turn girdiği son adım ile en son konuşulan adım aynı olmalı". Kapanış turu sessiz `end_call` ile bitiyor (konuşan son adım `closing_say`, sonra `close_record`, `end_call` düğümü girişleri). Kendi sentetik kaydımla denedim: kullanıcı mesajı yeni, `closing_say` cümlesi var, `node_enter end_call` var, çağrı bitmiş (`endedReason`) → durum **`turn_state_lost`** (bitmiş işaretlenmesi de fark etmedi). Sonuç: kapanış turunda bir 504 gelirse (F-023 tam olarak bunu yaşadı) `third_party_close` vakası doğrulanmadan `platform_error` ile bitiyor.
- **Düzeltme:** karşılaştırmayı, çağrı bittiyse (`_ended`) ya da turn sessiz bir terminal düğümde (`end_call`) bittiyse, turn içinde *konuşan* son adıma (mesajın `nodeId`'si) göre yap; sessiz passthrough/terminal düğümleri `entered[-1]` olarak sayma. Test: kapanış turu + 5xx → `turn_processed`.
- Etki sınırlı: yalnızca 5xx'li kapanış turunu etkiliyor; yanlış yönde güvenli (yeniden gönderme yok).

## Doğrulananlar

**F-045 (başlangıç adımında `node_enter` yok):** `_reached_nodes` bir adımı şu durumlarda ulaşılmış sayıyor: `node_enter`, herhangi bir mesajın `nodeId`'si, `workflowSnapshot` (`currentNode`, `previousNode`, `enteredNodes`) ya da `INITIAL_NODE` ve çağrıda konuşulmuş mesaj var. `INITIAL_NODE = "opening"`; testler üç fixture'ın render edilen `initial_node`'u ile eşitliği doğruluyor (sabit ile workflow kayması sessiz olmaz). Yasak düğüm kontrolü (`account`) aynı kümeyi kullandığı için `previousNode`/`enteredNodes` üzerinden de yakalıyor.

**F-046 (makul cevaplar):** `_plausible_answer(field, answer_format, ask)` alan adına, cevap biçimine ve soruya bakıyor: tarih ipuçları (`YYYY`, `DD`, "date", "birthday", "DOB") → "It's the third of March, nineteen eighty-five."; "year" → "Nineteen eighty-five."; "N digits" → rakamlar ("They are 4 8 2 1."); "postcode/postal/zip" → postcode benzeri; "e-mail" → e-posta; aksi "It's 4821." Kurallar genel sözcüklere dayanıyor, brief değeri yok; soru metni artık müşteri cümlesine yankılanmıyor. Cevaplar bilerek yanlış (banka sahte müşteriyi reddediyor), amaç ajanın dönüştürüp `verify_identity`'yi çağırması. Not: `birth_year` gibi bir alanda biçim `YYYY` olunca tarih dalı ("third of March, 1985") seçiliyor; yıl içeriyor, ajan yine yıl çıkarabilir, kabul.

**F-049 (5xx'te durum kaybı):** `_turn_state` üç sonuç veriyor: `turn_absent` (mesaj kayıtta yok → yeniden gönder), `turn_processed` (mesaj yeni, yanıt var ya da çağrı bitti ve son konuşulan adım turun girdiği son adımla aynı), `turn_state_lost` (mesaj kayıtlı ama yanıt yok ya da tur bir adıma girdi, son mesaj eski adımda kaldı) → araçlar çalışmış olabileceği için **yeniden göndermiyor**, vakayı `platform_error` yapıyor. Normal çok adımlı tur (kimlik cevabı → sessiz `account` → `negotiate` konuşur) doğru `turn_processed`; cevapsız tur `turn_state_lost`. İlke F-023/F-049 ile uyumlu (çift araç çağrısı riskini almıyor). Bulgu 1 dışında doğru.

## Kurallara uyum
Yalnızca `selftest.py` ve testi değişmiş; brief değeri yok; Freya/model isteği yok. Rapordaki TO-CONFIRM'ler geçerli: ajan `verify_identity`'yi bu cevaplarla çağırıyor mu, üç vaka `identity`/`third_party`'yi ulaşılmış gösteriyor mu, gerçek bir 5xx kaydı fixture olarak saklanmalı.
