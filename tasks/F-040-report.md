# F-040 raporu: extraction'ı yeni alanlara ve çerçeve durumlarına göre güncelleme

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

Durum:

- **Testler:** `python3 -m unittest` yeşil. `tests.test_extract` 41 testin hepsini geçiyor (öncesi 32). Testler offline ve kayıtlı cevaplarla çalışıyor.
- **Değişen dosyalar:**
  - Kod: `builder/extract.py`, `builder/prompts.py`, `tools/compare_spec.py`.
  - Doküman: `docs/PROMPTS.md` (yeniden üretildi), `docs/UAT-FINDINGS.md` (F-040 durumu).
  - Testler: `tests/test_extract.py`, `tests/extract_helpers.py`, `tests/fixtures/extract/brief-a-replies.json`.
  - T-006b referansları: `tests/briefs/*/reference-spec.json` ve `expected.md`.
- **Dokunulmayanlar:** `workflow.py`, `offer_check.py`, `spec.py`, fixture A/B/synthetic. Çalışma ağacında `build.py`, `freya.py` ve `selftest.py` de değişmiş görünüyor; onlar başka bir görevden (T-007), dokunmadım.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok, canlı çağrı yok.

## 1. `offer.next_weekday`

- **Prompt (`EXTRACT_OFFER_TASK`):**
  - `following_week`: bir sonraki takvim haftasındaki o gün.
  - `upcoming`: bugünden sonraki en yakın o gün.
  - Bu ikisi yalnızca dokümanlar "next <weekday>"i tanımlıyorsa kullanılır; tanımlamıyorsa `ask` (ajan hangi tarihi kastettiğini sorar).
  - Kaynak `sources["offer.next_weekday"]`'e yazılıyor.
- **Kod kontrolü:** Değer `ask` değilse dokümanlarda "next" kelimesinin ardından bir gün adı, `weekday` ya da `<weekday>` geçmeli; geçmiyorsa hata ve onarım. `ask` her zaman geçerli. Alan hiç gelmezse `spec.py` zaten `ask` varsayıyor.

## 2. `offer.max_rejected_offers` ve `max_rejected_offers_by_product`

- **Prompt:**
  - Alan açıkça tanımlanıyor: bir ürünün tarih veya tutar kontrolünden geçemeyen farklı teklif sayısı, ürün bundan sonra bırakılır. En az 2.
  - Bu sayı reddedildikten sonraki persuasion attempt sayısı **değil**; persuasion ya da attempt sayısı buraya kopyalanmaz.
  - Dokümanlar geçersiz teklif için bir sınır koymuyorsa değer 2, kaynak `fallback: no invalid-offer limit in the documents`.
  - `max_rejected_offers_by_product` yalnızca dokümanlar ürün grubuna göre farklı geçersiz teklif sınırları koyuyorsa doluyor; yoksa `[]`. "Banda göre persuasion attempt sayısı geçersiz teklif sınırı değildir" cümlesi prompt'ta açıkça yazıyor.
- **Kod kontrolü:**
  - İki alandan birinin kaynağı persuasion veya attempt içeren bir alıntıysa hata ve onarım; mesaj alanın anlamını yeniden anlatıyor.
  - 2'nin altındaki değerleri `spec.py` reddediyor; hata `max_rejected_offers_by_product[0].value` yoluyla offer grubuna gidiyor (testli).

## 3. Brief'in adını koymadığı çerçeve bitiş durumları

- **Zorunlu eşleme:**
  - `account_failed`, `offer_limit`, `hangup` ve `hangup_unverified` artık her spec'te bir satıra eşlenmek zorunda (`DERIVED_REQUIRED_STATES`). Eşlenmezse onarım mesajı gidiyor: "en yakın satıra eşle ve `derived_states`'e yaz".
  - Prompt (`CLOSE_STATE_GUIDE`) bu dört durumu "required" olarak işaretliyor; `offer_limit` için "genellikle ret satırı" ipucu var.
- **`derived_states`:**
  - Outcomes cevabı `derived_states: {durum: neden}` alanını taşıyor. Alıntı gerekmiyor, kısa bir neden yeter.
  - Kod iki şeyi kontrol ediyor: her derived durumun bir satıra gerçekten eşlenmiş olması ve nedenin boş olmaması.
  - Merge bunları `provenance["outcomes.state.<durum>"] = "derived: <neden>"` olarak yazıyor.
- **Açılışta ret:**
  - Açılış cevaplarında, konuşmak ya da kim olduğunu doğrulamak istemeyen kişi için route `end` olan bir değer artık zorunlu.
  - Bu değer dokümanların doğrulama öncesi ret satırına, yoksa en yakın satıra kapanıyor.
  - Doküman bu durumu adlandırmıyorsa kaynağı `derived: …` olabiliyor; provenance'a `outcomes.state.opening:<değer>` olarak geçiyor.
  - Alıntı kontrolü `derived` önekini `fallback` gibi atlıyor.
- **Karşılaştırma aracı:** Çalışma anında eşlenmemiş isteğe bağlı bir durum zaten `default` satırını kullanıyor. Araç da artık böyle sayıyor; açıkça `default` satırına eşlemek ile hiç eşlememek aynı kabul ediliyor. Böylece elle yazılmış fixture'larla karşılaştırmada yalnızca gerçek davranış farkları görünüyor.

## Ek koruma (canlı spec'lerde gördüğüm sorun)

Dört canlı çıkarmada da model, araç gerektiren durumları (`insists_on_human`, `requests_restructuring`, `hardship_accepted_support`) ve ödendi/itiraz durumlarını **pazarlık niyeti** olarak route `end`'e koymuş. Bu, örneğin `transferred/human` ile `transfer_to_agent` hiç çağrılmadan kapanış ya da "ödemeler bir iş günü sürebilir" cümlesi söylenmeden kapanış demek.

- **Prompt (`EXTRACT_FLOW_TASK`):** Route `end` yalnızca ödemeyi veya konuşmayı reddetmek için kullanılır. Kendi cümlesi ya da aracı olan durumlar özel yollardır ve buraya yazılmaz.
- **Kod (gruplar arası):** Bir pazarlık değeri, aracı olan bir özel yolun kapandığı outcome/reason çiftiyle kapanıyorsa hata ve onarım ("bu yolu özel yol kendi aracını çağırarak kapatıyor"). Araçsız durumlar (ödendi, itiraz) yalnızca prompt ile korunuyor: ret satırı "iki kez konuşmak istemiyorum" gibi meşru araçsız yollarla paylaşılabildiği için kodla ayırt edilemiyor.

## Test verisi güncellemeleri

- **Kayıtlı Brief A cevapları:**
  - `offer_limit` ve `hangup` ret satırına eklendi (davranış aynı: daha önce de `default` satırına düşüyorlardı).
  - Dört durum `derived_states` olarak yazıldı.
  - `next_weekday` kaynağı ve geçersiz teklif sınırının fallback kaynağı eklendi.
- **Round-trip yardımcısı:** Fixture'ın eşlemediği zorunlu çerçeve durumlarını açıkça `default` satırına eşleyip `derived_states`'e yazıyor. Fixture'lara dokunulmadı.
- **T-006b referansları:** Geçersiz teklif sınırı persuasion+1 değerlerinden (2/3 ve 3/2/3) **`2` ve `[]`**'e çekildi; iki brief de geçersiz teklif sınırı koymuyor. `expected.md` dosyalarına bu not eklendi. İki referans da `spec.py` doğrulamasından geçiyor.

## Yeni testler (9)

- Türetilmiş durumlar eşleniyor ve provenance'ta `derived: …` olarak duruyor; uyarı üretmiyor.
- Eşlenmemiş `offer_limit` onarıma gidiyor; mesajda `derived_states` geçiyor.
- Satıra eşlenmemiş bir derived durum hata veriyor.
- Açılışta ret değeri zorunlu; `derived` kaynağı provenance'a geçiyor.
- Aracı olan özel yolun çiftiyle kapanan pazarlık değeri onarıma gidiyor.
- `next_weekday`: Brief A'da geçerli; "Next <weekday>" satırı silinince hata veriyor; `ask` her zaman geçerli.
- Persuasion alıntısı gösteren geçersiz teklif sınırı hata veriyor; fallback kaynağı geçiyor.
- `by_product` değeri 1 olunca offer grubuna onarım gidiyor.
- Karşılaştırma aracı: açık `default` eşlemesi eşlemesizle aynı sayılıyor; farklı bir satıra eşleme fark olarak çıkıyor.

## Canlı tekrar (CTO) ve beklenen sonuçlar

Komutlar değişmedi: `tasks/T-006-report.md` (A, A+B) ve `tests/briefs/README.md` (raw-a, changed-a).

Beklenenler:

| Alan | Beklenen değer |
|---|---|
| `offer.next_weekday` | A, A+B ve raw-a'da `following_week`; changed-a'da `upcoming` |
| `offer.max_rejected_offers` | dört brief'te de `2` |
| `offer.max_rejected_offers_by_product` | dört brief'te de `[]` |
| `opening.close_values` | en az bir ret değeri, doğrulama öncesi ret satırına kapanıyor: `not_verified/declined`, changed-a'da `unverified/refused_check` |
| `provenance` | `outcomes.state.{account_failed, offer_limit, hangup, hangup_unverified}` girdileri `derived: …` ile başlıyor |
| `negotiation.intents` | transfer, ödendi veya itiraz değeri yok; bunlar özel yollarda |

## Kararınız gereken nokta

**Fixture A ve B persuasion+1 kullanıyor.** Fixture A'da (Codex'in T-005g düzeltmesi) `max_rejected_offers_by_product` değerleri hâlâ 2/3. Yeni kurala göre extractor `[]` üreteceği için A ve A+B karşılaştırmasında `offer.max_rejected_offers_by_product` satırında **bir DIFF bekleniyor**.

- Brief A geçersiz teklif sınırı koymuyor. Bu yüzden fixture'ın da `[]` olması tutarlı olur; T-005g review'ın "ya da hiç by_product kuralı olmayıp skaler 2" seçeneği bu.
- Fixture Codex'in dosyası ve `workflow`/`offer_check` testleri ona bağlı olabilir; dokunmadım. Karar ve değişiklik sizin ya da Codex'in.

## Fix (review F-040 ve canlı koşu ilk tur hataları)

**Bulgu 1: `overrides` döngüsü (regresyon).**

- `overrides.extend` satırı yeniden grup döngüsünün içinde; türetilmiş durum blokları döngüden sonra.
- Canlı raw-a spec'indeki 6 override aslında outcomes grubunun 2 override'ının üç kez kopyalanmış haliydi; bulguyu doğruluyor.
- Test: dört grupta birer override var; birleşik listede dördü de birer kez geçiyor.

**Bulgu 2: `derived` yalnızca türetilmiş durumlarda.**

- `excerpt()` artık `derived: …` önekini yalnızca `derived_ok` verilen yerde kabul ediyor: route'u `end` olan açılış, üçüncü kişi ve pazarlık değerlerinin `source` alanı.
- `derived_states` zaten alıntı istemiyor.
- Kural kaynaklarında (`*.rules[i]`, `when`, `say`, `ask`, `introduction` vb.) `derived` ya da `fallback` gelirse hata ve onarım: "kural kaynağı dokümandan alıntı olmalı".
- `fallback` yalnızca `sources` haritasındaki veri alanlarında kaldı.
- Test: kural kaynağında `derived` ve `fallback` hata veriyor; aynı turda route `end` değerindeki `derived` kaynağı hata vermiyor.

**Bulgu 3: `next_weekday` yön kanıtı.**

- Kod "next <weekday>" geçen satırlarda yönü belirten bir sözcük arıyor:
  - `following_week` için: `following`, `week after`, `next (calendar) week`;
  - `upcoming` için: `nearest`, `upcoming`, `coming`, `soonest`, `first`, `next such`.
- Bulamazsa hata ve onarım ("yön dokümanla uyuşmuyor"). Tanımsız, yalnızca örnek olarak geçen "next Friday" da reddediliyor. `ask` her zaman geçerli.
- Test:
  - Brief A + `upcoming` → hata;
  - changed-a + `following_week` → hata;
  - doğru eşleşmeler geçiyor;
  - yalnızca örnek cümle olan bir brief → hata.

**İlk turdaki yüksek hata sayısı (Brief A 18, raw-a 37; F-041).**

- **Eldeki kanıt:** Trace'te yalnızca hata sayıları vardı, metinler yoktu. Yine de canlı spec'ler güçlü bir ipucu veriyor:
  - Onarımdan sonra kapanan özel yolların neredeyse hepsinde `ask` dolu, ama soru değil talimat: "Take no promise.", "Do not describe a plan.", "Ask nothing else.".
  - Brief A'da 9 özel yol var ve ilk tur tam 18 hata verdi. Bu, yol başına boş bir `ask` nesnesinin (`text` ve `source` boş) iki hata üretmesiyle birebir uyuşuyor.
  - Onarım mesajı yalnızca "boş olmamalı" dediği için model alanları sildirmek yerine talimatla doldurmuş.
  - Bu bir davranış hatası: iskelet `ask`'ı müşteriye soru olarak söyleyip cevap bekliyor.
- **Kod:**
  - Metni boş `ask` merge'de düşürülüyor (hata sayılmıyor).
  - Dolu `ask` "?" ile biten tek bir soru olmalı; değilse onarım mesajı nedeni ve çözümü söylüyor (talimatlar `when`/`say`'e).
- **Prompt (`EXTRACT_OUTCOMES_TASK`):**
  - `ask` ne zaman konmaz: yalnızca dokümanlar eylemden önce bir soru istiyorsa kullanılır, müşteriye söylenip cevap beklenir, asla talimat değildir.
  - JSON şablonunun ardından "Code checks this reply" listesi geliyor; kodun bu grupta uyguladığı altı kontrolü tek tek sayıyor:
    - kural kaynakları alıntı;
    - outcome/reason çifti tek satırda;
    - özel yol çiftleri tabloda;
    - `tool_args` enum'da;
    - her durum tek satırda;
    - `ask` soru.
- **Trace:** Her turun hataları artık `extract_issue: round=N [grup] yol: mesaj` olarak yazılıyor (en fazla 60 satır). Bir sonraki canlı koşuda ilk tur hata türleri doğrudan görülecek.
- **Canlı spec'lerle doğrulama:** Mevcut dört canlı spec yeni kontrollerden geçirildi. Yalnızca talimat içeren `ask` alanları hata veriyor (Brief A 6, A+B 2, raw-a 11, changed-a 2). `derived` kapsamı ve `next_weekday` yönü dördünde de hatasız.
- **Test:**
  - Boş `ask` onarıma gitmiyor ve spec'te `ask` yok.
  - Talimat `ask` onarıma gidiyor.
  - `extract_issue` satırı yazılıyor.

**Fixture A ve B: `max_rejected_offers_by_product = []`, skaler 2.**

- Fixture B'nin tek satırlık biçimi korundu (yalnızca değer değişti). Kayıtlı Brief A cevapları da aynı değerle güncellendi.
- **`tests/test_multi_step.py`:** `test_rejection_limit_is_selected_by_product_band` fixture'daki bant kurallarına dayanıyordu.
  - Test artık bant kurallarını kendisi veriyor (`run_offer(..., offer=...)` ile fixture'ın offer alanlarının üstüne yazılıyor). Mekanizma testi korunuyor ve bu kuralların sentetik olduğu yorumda yazıyor.
  - Yeni test: fixture ile her ürün skaler 2'yi kullanıyor (ilk geçersiz teklif `rejected`, ikincisi `limit`).
- `workflow.py`, `offer_check.py`, `build.py` ve `selftest.py`'ye dokunulmadı.

**Sonuç:**

- **Testler:** `python3 -m unittest` 166 testin hepsini geçiyor; `test_extract` 45. `docs/PROMPTS.md` yeniden üretildi.
- **UAT:** F-041 eklendi (onarımın boş soruları talimatla doldurması).
- **Canlı tekrarda bakılacaklar:**
  - ilk turdaki hata sayısı ve `extract_issue` satırları;
  - `ask` alanlarının yalnızca gerçek sorular olması (insan talebinde "önce yardımcı olabilir miyim?", zorlukta "destek ekibine bağlayayım mı?");
  - raw-a'da `overrides` sayısının 2 olması (memo).
- Freya yok, commit yok, `env.sh` yok, canlı çağrı yok.
