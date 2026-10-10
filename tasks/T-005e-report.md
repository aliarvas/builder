# T-005e raporu: söz alma yolu düzeltmeleri

**Geliştirici:** codex-dev · **Tarih:** 2026-10-10

## Sonuç

Version 8 chat testlerinde görülen F-025..F-031 için builder düzeltildi. Freya'ya istek gönderilmedi, `env.sh` okunmadı, commit atılmadı ve `builder/` içine brief değeri eklenmedi.

Tam offline paket yeşil: 104/104 test. `builder/*.py` ve `tests/*.py` derleniyor, sızıntı taraması geçiyor, `docs/PROMPTS.md` kaynakla aynı ve en büyük step prompt tahmini 598 token (sınır 1.500).

## Bulgu başına değişiklik

### F-028 — düzleştirilmiş ürün değişkenleri

- Tek ürün okuyucu; mapped listeyi, JSON listeyi, düz anahtardaki listeyi ve Freya'da gözlenen `get_account_response.data.<liste>.<indeks>.<alan>` anahtarlarını destekliyor.
- Okuyucu ürünleri indeks sırasıyla yeniden kuruyor ve iç içe alan yollarını da koruyor.
- Aynı davranış teklif kurulumu/kontrolü, ürün numarası hook'u ve ürünlü özel yol ilerlemesinde kullanılıyor. Promise progress ayrıca düz veya JSON nesne biçimindeki tool args/result değerlerini okuyabiliyor.
- Tek ürün varsa ürün numarası verilmemiş olsa da otomatik olarak ürün 1 seçiliyor.
- Bir, iki ve üç ürünlü düzleştirilmiş fixture testleri doğru facts, verdict ve internal id üretiyor.

### F-026 — çağrının `now` değişkenine göre tarih

Seçim: extractor'a tarih çözdürmek yerine müşteri ifadesini string olarak aynen çıkarttırıp code step'te çözmek. Böylece Freya'nın gerçek saatine bağlı `date` extraction kullanılmıyor.

- Referans gün spec'teki `offer.today_variable` (fixture'larda `now`); yalnızca bu değişken yoksa sistem tarihi fallback.
- Çözücü `today`, `tomorrow`, `this <weekday>`, `next <weekday>`, `<weekday> the week after next`, `<weekday> the <day-number>`, ay adı içeren açık tarihler ve ISO tarihleri destekliyor.
- İş günü ve tatil kontrolü çözümden sonra mevcut spec takvimine uygulanıyor.
- Sabit `now` tablosu bugün, yarın, bu Cuma, gelecek Pazartesi, sonraki haftadan sonraki hafta + gün, açık tarih ve tatili kapsıyor.

### F-027 — sözlü tutar türleri

- Extraction'a generic `offer_amount_kind` eklendi: `full`, `minimum`, `other`.
- “Full/entire amount” spec'in `max_amount` kuralından; “minimum/required instalment/instalment amount” spec'in `min_amount` kuralından sayıya çevriliyor.
- Sayısal tutarlar eskisi gibi doğrudan kullanılıyor. Fixture'larda kredi kartı ve kredi için farklı minimum kaynakları test edildi.

### F-030 — dürüstlük

- Global prompt, `create_promise` sonucu `ok=true` olmadan ödeme/söz kaydı; ilgili tool sonucu `ok=true` olmadan not veya callback kaydı iddiasını yasaklıyor.
- `negotiate`, non-ok `offer_verdict` durumunda `offer_message` cümlesini önce söylemek ve kontrol edilmiş teklifi “kaydedilmiş” diye sunmamak zorunda.
- Model alanı gerektiren özel yol tool'u önce çağırıyor; yalnızca başarılı sonuçtan sonra spec cümlesini söylüyor.

### F-029 — erken refusal

- Negotiation intent description, spec'in `close_values` değerlerini yalnızca alternatif sorulduktan sonra her türlü ödeme/arrangement reddi olarak tanımlıyor.
- “Not today”, “not now”, tarih belirsizliği veya tek bir tarihte ödeyememe açıkça refusal sayılmıyor; prompt başka tarih sormayı emrediyor.
- Ek bir sayaç/“mutlaka bir counter-question” state'i eklenmedi; semantic extraction ve konuşma prompt'u kullanıldı.

### F-025 — internal id'nin okunması

- Customer facts metni configured internal product-id alanını dışarıda bırakıyor.
- Negotiation prompt'u raw account result veya internal id okumayı yasaklıyor; ürün tipi, customer-facing label ve gerekiyorsa liste numarasını kullanıyor.

### F-031 — ikinci `close_call`

- `closing_say`, `close_call_ok` true/True ise `close_attempt` ve `close_record` adımlarını atlayıp doğrudan `end_call`'a gidiyor.
- Normal kapanış ve iki denemeli hata yolu değişmedi. Graph testleri yalnızca bu guarded doğrudan kenara izin veriyor.

## Testler

- `python3 -m py_compile builder/*.py tests/*.py` — geçti.
- `python3 -m unittest discover -s tests -v` — 104/104 geçti.
- Source leakage testi — geçti.
- Prompt document güncellik testi — geçti; `docs/PROMPTS.md` yeniden üretildi.
- Prompt bütçesi — fixture A 598, fixture B 564, synthetic 496 token maksimum.
- `git diff --check` — geçti.

İlk tam test koşusunda kapanış grafiğinin eski beklentileri ve henüz üretilmemiş prompt belgesi nedeniyle 7 test kırıldı; F-032 olarak kaydedildi, beklentiler F-031 sözleşmesine göre güncellendi ve ikinci tam koşu tamamen geçti.

## Açık sorular / Freya retest

- String extraction açıklamasının Freya modeline relative date ifadesini gerçekten değiştirmeden bıraktırdığı chat'te doğrulanmalı.
- Non-ok verdict'in model tarafından her seferinde `offer_message` ile seslendirilmesi ve “recorded” iddiası yapılmaması chat'te doğrulanmalı.
- Refusal için hard state counter eklenmedi. Semantic açıklama yetersiz kalırsa sonraki adım, spec-driven bir “alternative asked” değişkeniyle close route'u guard etmektir.
- `end_call` sonrasında chat route'una yeni mesaj gönderildiğinde `closing_say → end_call` guard'ının platformda ikinci `close_call` üretmediği doğrulanmalı.
- Bu maddeler CTO onaylı Freya chat retest gerektirir; bu görevde Freya çağrısı yapılmadı.

## Fix — CTO review düzeltmeleri

`reviews/T-005e-review.md` kararı sonrası zorunlu bulgular kapatıldı:

- **Bulgu 1:** Sabit `get_account_response` öneki kaldırıldı. Tek ortak üretilen okuyucu artık herhangi bir `<ad>_response.data.<products_field>.<index>.<field>` kalıbını okuyor. Teklif kurulumu/kontrolü, `workflow.py` ürün-numarası hook'u ve özel yol ilerlemesi aynı okuyucuyu kullanıyor. Mapped liste, JSON liste ve response altındaki liste fallback'leri korundu. Testler hem gözlenen `account_response.*` hem `get_account_response.*` biçimini bir, iki ve üç ürünle kapsıyor.
- **Bulgu 2:** `next week` + gün adı bir sonraki haftanın Pazartesi'sinden hesaplanıyor; gün adı yoksa `missing`. Aynı haftaya düşen belirsiz `next <weekday>` artık teklifi kabul etmiyor ve örneğin `Do you mean Friday 16 October?` sorusunu üretiyor. `the day after tomorrow`, üç harfli ay ve yalnız gün numarası desteği eklendi.
- **Bulgu 4:** Extraction açıklamasından `{{today_text}}` kaldırıldı; relative tarih çözümü yalnızca code step'te call `now` değerine göre yapılıyor.
- **Bulgu 3:** Review talimatına uygun olarak deterministik refusal sayacı eklenmedi; chat retest maddesi olarak kaldı.

Düzeltme sonrası `python3 -m py_compile builder/*.py tests/*.py` ve tam offline paket geçti: 104/104. `docs/PROMPTS.md` yeniden üretildi. Freya isteği yapılmadı, commit atılmadı ve `env.sh` okunmadı.
