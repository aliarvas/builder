# T-006 raporu: spec'i brief'ten çıkarma

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

Builder artık spec'i `brief + OpenAPI`'den kendisi çıkarıyor. `python3 builder/build.py {brief} {openapi}` komutu `--spec` olmadan çağrıldığında şu adımları izliyor:

1. model çağrılarıyla spec'i çıkarıyor;
2. spec'i kodla doğrulayıp gerekirse onarıyor;
3. kapsamayı kontrol ediyor;
4. sonucu `traces/<slot>.spec.json`'a yazıyor;
5. normal build'e devam ediyor.

`--spec` aynen çalışıyor. Eski tek adımlı ajan artık yalnızca `--single-step` bayrağıyla açılıyor.

Durum:

- **Testler:** `python3 -m unittest` 128 testin hepsini geçiyor (öncesi 104). 24 yeni test var ve hiçbiri ağa çıkmıyor.
- **Diğer kontroller:** `py_compile` ve `git diff --check` temiz. `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:**
  - Canlı Anthropic çağrısı yapmadım; komutlar aşağıda.
  - Freya'ya istek yok, commit yok, `env.sh` okunmadı.
  - Anahtar hiçbir yere yazılmıyor.
  - `builder/` içinde brief değeri yok; sızıntı testi ve yeni prompt testi yeşil.

## Değişen dosyalar

- **Yeni:**
  - `builder/llm.py`: stdlib `urllib` ile Anthropic istemcisi.
  - `builder/extract.py`: çıkarma, doğrulama, onarım ve kapsama.
  - `tools/compare_spec.py`: karşılaştırma aracı.
  - `tests/test_extract.py`, `tests/extract_helpers.py`.
  - `tests/fixtures/extract/brief-a-replies.json`: kayıtlı model cevapları.
- **Değişen kod:**
  - `builder/build.py`: çıkarma adımı, `--single-step`, trace satırları.
  - `builder/prompts.py`: 10 yeni extraction prompt'u.
  - `builder/run_trace.py`: token alanları ve Anthropic anahtarını maskeleme.
  - `builder/tools_from_openapi.py`: `tool_contract()`, yani extractor'ın gördüğü kompakt araç sözleşmesi.
- **Değişen testler:**
  - `tests/test_vertical_slice.py`: tek adımlı CLI testleri artık `--single-step` ile çalışıyor.
  - `tests/test_multi_step.py`: sızıntı testinde API blok anahtar kelimesi için dosya izni (F-035).
- **Doküman ve ayar:** `docs/PROMPTS.md`, `docs/UAT-FINDINGS.md` (F-035, F-036), `docs/ARCHITECTURE.md` (bir satır), `.gitignore`.

`spec.py` sözleşmesine dokunmadım. T-005 serisinde eklenen alanların hepsi `parse_spec` ve kuru render ile doğrulanıyor. T-005e spec'e alan eklememiş; değişiklikleri renderer'daydı.

## Tasarım

### İstemci (`builder/llm.py`)

- **Bağlantı:** Messages API'ye `urllib` ile gidiyor. Anahtar istek anında `ANTHROPIC_API_KEY`'den okunuyor; yoksa açık bir hata veriyor.
- **Model ve ayarlar:** Model tek yerde sabit: `EXTRACTION_MODEL = "claude-sonnet-5-5"`. `temperature` 0, `max_tokens` 16000, zaman aşımı 300 sn.
- **Yeniden deneme:** Ağ hatası, zaman aşımı, 429 veya 5xx/529 durumunda bir kez yeniden deniyor. Hata mesajları anahtardan arındırılıyor.
- **Sıcaklık reddi:** Model `temperature`'ı 400 ile reddederse istek bir kez onsuz gönderiliyor (TO-CONFIRM 1).
- **Çıktı sınırı:** `stop_reason = max_tokens` hata sayılıyor; yarım JSON kullanılmıyor.
- **Trace:** Her çağrı trace'e bir satır yazıyor: `model_call: model=… purpose=… input_tokens=… output_tokens=… [cache_read_tokens=…] duration_seconds=…`. Sonunda toplam bir satır geliyor: `model_calls: N input_tokens output_tokens model_seconds extract_seconds`.
- **Maskeleme:** `TraceWriter` ve `build._error_text` artık `ANTHROPIC_API_KEY` değerini ve `sk-ant-…` desenini maskeliyor.

### Bölümlere ayrılmış çıkarma (`builder/extract.py`)

| Çağrı | Bölümler |
|---|---|
| `opening_identity` | agent, opening, third_party, identity, global_rules |
| `flow` | account, negotiation, confirmation |
| `offer` | offer: takvim, tatiller, en erken ve en geç tarih kuralları, alt ve üst tutar, ret limiti |
| `outcomes` | outcomes tablosu, special_paths, closing |

Çağrıların yapısı:

- **Ortak bağlam:** Her çağrı aynı ortak bağlamı alıyor:
  - sıralı dokümanların tamamı ("Document 1 of 2: …");
  - OpenAPI'den kompakt araç sözleşmesi (~800 token: istek/cevap alanları, enum'lar, açıklamalar);
  - çağrı değişkenleri;
  - iskeletin kısa tarifi.
  Bu blok `cache_control` ile önbellekleniyor; onarım ve kapsama çağrıları onu tekrar kullanıyor.
- **Bağımsızlık:** Dört çağrı birbirine bağımlı değil; bu yüzden **paralel** koşuyorlar (thread). Bunu sağlayan bir ara biçim var:
  - Açılış cevapları, üçüncü kişi niyetleri ve pazarlık niyetleri `route` (verify / other_person / ask_again / end …) ile geliyor.
  - Çağrıyı kapatan her değer kendi `outcome/reason` çiftini taşıyor.
  - Merge kodu bunları spec'in değer listelerine ve `outcomes[].on` girdilerine çeviriyor (`opening:<v>` vb.). Böylece outcomes çağrısının açılış değerlerinin adını bilmesi gerekmiyor.
- **İskelet adları kodda:** Değişken adları ve sentetik alan adları (`who_answered_variable`, `*_intent` değişkenleri, `products_variable`, `product_number_field`…) modelden değil koddan geliyor: `FRAMEWORK_NAMES`. Adlar hiçbir fixture değeriyle çakışmayacak şekilde seçildi.
- **Kaynak:** Her kuralın `source` alanı brief'ten kelimesi kelimesine bir alıntı.
  - Veri alanlarının kaynağı `sources` haritasına gidiyor. Brief vermiyorsa değer "fallback: neden" olarak işaretleniyor.
  - Üstüne yazma ilişkileri ("memo eskiyi değiştirir") `overrides` listesine yazılıyor.
  - Bu bilgiler spec'te `provenance` ve `overrides` olarak duruyor; `parse_spec` bu anahtarları yok sayıyor.
- **Hesap kodda:** Model hesap yapmıyor. "12. iş günü" gibi kurallar `{days, unit}` olarak geliyor; hesabı mevcut offer kodu yapıyor.

### Çağrı planı ve süre

```
4 çıkarma çağrısı (paralel)
  → doğrulama
  → 0–2 onarım turu (yalnız hatalı gruplar, tur içinde paralel)
  → 1 kapsama çağrısı
  → 0–1 hedefli tekrar sorma
```

- **Çağrı sayısı:** En az 5, en çok 4 + 8 + 2 = 14 çağrı.
- **Süre tahmini (ölçülmedi):** Paralel ilk tur ~60–90 sn, kapsama ~60 sn, her onarım turu ~30–60 sn. Hedef olan 5 dakikanın altında kalması bekleniyor. Gerçek süre trace'teki `extract_seconds` alanında görünecek.

## Doğrulama ve onarım kuralları

**Grup biçimi (ara biçim):**

- zorunlu nesneler ve kural biçimi (`text` ile `source`);
- route değerleri geçerli;
- açılışta en az bir verify ve tam olarak bir ask_again var;
- pazarlıkta readback var;
- onayda record ve change var;
- değerler snake_case ve tekrarsız; `greeting` değeri ayrılmış;
- sayılar pozitif tam sayı;
- adres ve "bugün" değişkenleri çağrı değişkeni;
- outcomes satırlarının `states` alanı yalnızca bilinen bitiş durumlarını içeriyor, her biri tek satırda;
- zorunlu bitiş durumlarının hepsi eşlenmiş (`opening_unclear`, `callback_scheduled`, `identity_failed`, `promise_recorded`, `promise_failed`, `default`).

**Gruplar arası:** Kapatan her route değerinin `outcome/reason` çifti tabloda bir satır olmalı. Hata mesajında mevcut satırlar listeleniyor.

**Birleşik spec (`check_spec_data`):**

- **Kimlik:**
  - soru alanlarının hepsi `verify_identity`'nin aynı enum'unda (artık uyarı değil hata);
  - `verified_field` ve `answer_verified_field` boolean, `attempts_left_field` integer cevap alanı.
- **Hesap ve kayıt alanları:**
  - `products_field`, `get_account` cevabında bir array;
  - `product_id_field` ürün öğesinin bir alanı;
  - söz alanları `create_promise` istek alanları;
  - sentetik ürün numarası alanı gerçek bir alanla çakışmıyor;
  - kapanış alanları `close_call` istek alanları.
- **Offer:**
  - koşul ve tutar alanları ürün alanları;
  - `in`/`equals` değerleri o alanın enum'unda;
  - tatil tarihi brief'te yazmıyorsa uyarı.
- **Kapanış tablosu:**
  - outcome `close_call` enum'unda;
  - outcome ve reason ya brief'te ya araç sözleşmesinde geçiyor (uydurma kod yakalanır);
  - aynı satır iki kez yok.
- **Özel yollar:**
  - araç gerçek bir araç ve rezerve araçlardan biri değil;
  - `tool_args` anahtarları o aracın istek alanları;
  - değerler enum'da, enum yoksa brief'te geçiyor;
  - araçsız yolda argüman yok;
  - id'ler tekrarsız.
- **Kaynaklar:** Brief'te bulunamayan alıntı uyarı olarak trace'e gidiyor; hata sayılmıyor.
- **Üstüne yazma:**
  - Eski (üstüne yazılmış) metni kaynak gösteren kural hata.
  - "Yeni" alıntı dokümanda eskiden önce geliyorsa uyarı.
- **Son kapılar:**
  - `parse_spec`: sayılar, ISO tarihler, takvim, `on` haritası ve diğer tüm sözleşme kuralları;
  - `build_spec_workflow` ile kuru render: renderer'ın kendi kontrolleri.

**Onarım:**

- Hatalar yollarına göre sahibi olan gruba gidiyor; yol bulunamazsa tüm gruplara.
- Onarım aynı konuşmanın devamı. Yeni mesaj yalnızca hata listesini içeriyor; brief ve önceki cevap zaten bağlamda.
- Geçersiz JSON da bir onarım turu sayılıyor.
- En fazla 2 tur. Sonunda hâlâ hata varsa build şöyle duruyor:
  - exit 2 ve `spec extraction failed after 2 repair rounds; N problem(s), first: …`;
  - her hata trace'te ayrı bir `extract_error: [grup] yol: mesaj` satırı;
  - aday spec `traces/<slot>.spec.failed.json`'a yazılıyor (git'te yok sayılıyor).
- Yarım ajan oluşmuyor.

## Kapsama yöntemi

1. **Kod:** Dokümanlar maddelere bölünüyor: cümleler, liste maddeleri ve tablo satırları. Başlıklar ve tablo ayırıcıları atlanıyor; Brief A'da 186 madde çıkıyor.
2. **Kapsama çağrısı:** Her madde için `covered` (spec yollarıyla), `not_relevant` veya `missing` istiyor.
   - Kod, yolların spec'te gerçekten bulunduğunu kontrol ediyor; çözülemeyen yol `missing` sayılıyor.
   - Modelin atladığı id'ler de `missing` sayılıyor.
3. **Hedefli tekrar sorma:** Eksik maddeler için tek bir çağrı.
   - Cevap ya bir ekleme (bir aşamanın kuralları, `global_rules`, `special_paths` veya `outcomes`) ya da "gerekmez, çünkü …".
   - Eklemeler önce topluca deneniyor. Spec bozulursa tek tek deneniyor, bozanlar atılıyor (`coverage_rejected`).
4. **Trace:**
   - `coverage: items covered not_relevant missing`;
   - `coverage_added`, `coverage_not_relevant`, `coverage_rejected`;
   - kalan her madde için `coverage_unmapped: <id>: <metin>`.
   Spec'te de `coverage.unmapped` olarak duruyor.
5. **Kapsama hatası build'i durdurmuyor.** Geçerli spec ile devam ediliyor ve bütün maddeler "doğrulanmadı" olarak trace'e yazılıyor (açık soru 4).

Trace ayrıca kuralların yaptırım katmanını özetliyor: `rule_tiers: code … ; step_prompt rules=N; global_prompt rules=M`.

## Testler (offline, ağ yok)

**Pipeline:**

- **Kayıtlı cevaplar:** Fixture A'dan üretilen kayıtlı cevaplar, karşılaştırma aracına göre fixture A ile **farksız** bir spec üretiyor.
- **Çok dokümanlı round-trip:** A + B dokümanlarıyla fixture B aynı şekilde farksız.
- **Paralellik:** Dört ilk çağrı bir `Barrier(4)`'te birbirini bekliyor. Sıralı çalışan bir pipeline'da bariyer kırılırdı.
- **Ortak bağlam:** Dört çağrıda bağlam aynı ve önbellek işaretli; görev metinleri farklı.

**Onarım ve hata yolu:**

- Bozuk outcomes cevabı (eşlenmemiş `identity_failed`, enum dışı kuyruk) yalnız o grup için tek onarımla düzeliyor. Onarım mesajı brief'i içermiyor ve aynı konuşmanın devamı.
- Merge sonrası bulunan sözleşme hatası (`special_paths[2].tool_args.queue`) doğru gruba gidiyor.
- Geçersiz JSON onarılıyor.
- Tabloda olmayan kapanış çifti, satır listesiyle birlikte geri gönderiliyor.
- **Hata yolu:** 2 onarım turundan sonra `ExtractionError`. Bütün sorunlar listeleniyor, kapsama çağrısı yapılmıyor ve trace'te `extract_error` satırları var.

**Kapsama:**

- Geçerli ekleme kabul ediliyor, bozan ekleme atılıyor.
- Çözülemeyen yol `unmapped` kalıyor.
- Unutulan id "gerekmez" cevabıyla kapanıyor.
- Kapsama hatası spec'i engellemiyor.

**Doğrulama kuralları:**

- Fixture A hatasız geçiyor.
- 11 ayrı sözleşme/kanıt hatası yakalanıyor.
- Üstüne yazılmış metne atıf hata veriyor.
- Madde bölme ve yol çözme doğru çalışıyor.

**İstemci:**

- Anahtar yoksa açık hata.
- İstek biçimi doğru (model, `temperature 0`, başlık).
- Ağ hatasında tek yeniden deneme; trace'e anahtar düşmüyor.
- İkinci hata anahtarsız mesajla yükseliyor.
- Sıcaklık reddinde istek onsuz yeniden gönderiliyor.
- `max_tokens` hata sayılıyor.

**Build entegrasyonu (sahte istemciyle `build.main`):**

- `--spec` olmadan çıkarma yapılıyor, `traces/<slot>.spec.json` yazılıyor.
- 5 `model_call` satırı ve toplam token satırı trace'te; anahtar hiçbir trace dosyasında yok.
- Doğrulama hatasında exit 2, `extract_error` satırları ve `spec.failed.json` dosyası oluşuyor; `spec.json` yazılmıyor.

**Prompt'lar genel:** Extraction prompt'larında fixture veya araç enum kodu, pratik brief örnek kelimesi ya da ISO tarih yok (F-036).

## Canlı çalıştırma komutları (CTO)

Anahtarın ortamda `ANTHROPIC_API_KEY` olarak tanımlı olduğu varsayılıyor. Bu komutlar Freya'ya gitmez (`--print`).

```bash
# Brief A
python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json \
  --print --slot t006-brief-a > /tmp/t006-brief-a.workflow.json
python3 tools/compare_spec.py traces/t006-brief-a.spec.json tests/fixtures/spec-brief-a.json
grep -E "^(model_call|model_calls|extract_|coverage|rule_tiers|warning|error)" traces/t006-brief-a.print.log

# Brief B (Brief A'ya atıf yaptığı için iki doküman sırayla verilir; sonraki öncekinin üstüne yazar)
python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/briefs/brief-b.md \
  build-the-builder-v2/tools/openapi.json --print --slot t006-brief-b > /tmp/t006-brief-b.workflow.json
python3 tools/compare_spec.py traces/t006-brief-b.spec.json tests/fixtures/spec-brief-b.json

# Tekrarlanabilirlik: aynı brief'i ikinci kez çıkar, iki sonucu karşılaştır
python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json \
  --print --slot t006-brief-a-2 > /dev/null
python3 tools/compare_spec.py traces/t006-brief-a-2.spec.json traces/t006-brief-a.spec.json
```

Başarısız olursa bakılacak yerler: `traces/<slot>.failed.log` dosyasındaki `extract_error` satırları ve `traces/<slot>.spec.failed.json`.

**Karşılaştırmayı okurken:** Fixture'lar elle yazıldı ve eksik. Örneğin fixture A'da üç özel yol var; Brief A'da yeniden yapılandırma, destek/zorluk ve not gibi başka yollar da geçiyor. Bu yüzden `special_paths` ve `outcomes.state` satırlarında fark beklenir. Önemli olan farklar:

- kimlik alanları ve sırası;
- offer takvimi ve kuralları;
- tablo satırları;
- kapanış durumlarının eşlenmesi;
- eksik zorunlu cümleler.

## TO-CONFIRM (canlı koşuda)

1. **Sıcaklık:** `claude-sonnet-5-5` `temperature: 0` kabul ediyor mu? Etmezse istemci bir kez onsuz gönderiyor. Trace'te ek bir çağrı süresi görünür.
2. **Önbellek:** Önbellekleme çalışıyor mu? Onarım ve kapsama çağrılarında `cache_read_tokens` görünmeli. İlk dört paralel çağrı önbelleği aynı anda yazdığı için onlarda isabet beklenmez.
3. **Süre:** Toplam `extract_seconds` 5 dakikanın altında mı?
4. **Çıktı boyutu:** 16000 token yetiyor mu? Brief A'da 186 maddelik kapsama cevabı en büyük çıktı.
5. **Kaynak alıntıları:** Kelimesi kelimesine mi geliyor? Gelmiyorsa trace'te çok sayıda `extract_warning … not found verbatim` görünür.

## Açık sorular

1. **Spec'in ifade gücü.** Brief'te olup spec'te birebir karşılığı olmayan durumlar var:
   - hardship için "kabul ederse transfer, etmezse no_promise/hardship" dalı;
   - Brief B'de ürün başına not ve kapanış önceliği;
   - pazarlıktaki band başına ikna denemesi sayısı.

   Extractor bunları en yakın biçimde (özel yol, `ask`, kural metni) temsil ediyor; kalan kısım kapsama raporunda görünecek. Gerekirse sonraki görevde spec'e alan eklenebilir (`spec.py` değişikliği).
2. **`max_rejected_offers` brief'te doğrudan yazmıyor.** Model bunu deneme sayılarından çıkarıyor ya da "fallback" olarak işaretliyor; `provenance` bunu gösteriyor. Kodla belirlenen sabit bir varsayılan mı istenir?
3. **Alıntı uyuşmazlığı şimdilik yalnız uyarı.** Hataya çevirmek uydurmayı daha sert yakalar ama onarım turlarını tüketebilir. Canlı koşudaki uyarı sayısına göre karar verilebilir.
4. **Kapsama başarısız olursa build devam ediyor.** Bu bilinçli bir seçim: geçerli spec, ajansız kalmaktan iyi. Kapsama zorunlu bir kapı olsun istenirse küçük bir değişiklik.
5. **Model sürümü.** `claude-sonnet-5-5` bir takma ad. Tekrarlanabilirlik için tarihli bir snapshot adı varsa `builder/llm.py`'deki tek sabite yazılabilir.
6. **Hata mesajı uzunluğu.** stderr'deki hata mesajı mevcut `_error_text` ile 300 karakterde kesiliyor. Tam liste trace'te.

## Fix (canlı koşu: paralel çağrılarda temperature 400, F-037)

- **Yeniden gönderme kararı:** Artık o isteğin kendi payload'ına bakıyor (`"temperature" in payload`), paylaşılan bayrağa değil (`builder/llm.py`). Payload her denemede bir kez kuruluyor; aynı anda 400 alan bütün paralel istekler yeniden gönderiliyor.
- **Paylaşılan ayar:** `self.temperature` lock altında okunup yazılıyor. Ayar düşürülünce bir kez not callback'i çağrılıyor; build bunu trace'e `warning: model … rejected the temperature setting` olarak yazıyor.
- **Yeniden deneme hakkı:** Temperature yüzünden yapılan yeniden gönderme, ağ hatası için ayrılan tek yeniden deneme hakkını tüketmiyor.
- **Varsayılan: hiç gönderme.**
  - `EXTRACTION_TEMPERATURE = None` (`llm.py`'de modelin yanında tek sabit, gerekçesi yorumda). Sabitlenen model bu ayarı reddettiği için istek temperature içermiyor.
  - Trace'te bir satır görünüyor: `model_settings: model=claude-sonnet-5-5 temperature=not sent max_tokens=16000 timeout_seconds=300`.
  - Tekrarlanabilirlik artık sıcaklığa dayanmıyor; kodla doğrulama ve onarıma dayanıyor. Bunu da karşılaştırma aracındaki ikinci koşu ölçecek.
- **Testler:** 130 testin hepsi geçiyor (öncesi 128).
  - Yeni test: dört paralel istek temperature ile gidiyor, bariyerde birlikte 400 alıyor. Dördü de onsuz yeniden gönderiliyor (toplam 8 istek), not yalnızca bir kez yazılıyor.
  - Yeni test: temperature yeniden göndermesinden sonra ağ hatası için tek yeniden deneme hakkı hâlâ kullanılabiliyor.
  - Varsayılan isteğin temperature içermediği ve trace'teki `model_settings` satırı test ediliyor.
  - Mutasyon kontrolü: eski paylaşılan bayrak koşulu geri konunca paralel test hata veriyor.
- **UAT:** F-037'nin durumu "fixed offline" olarak güncellendi; canlı tekrar testi bekleniyor.
- Komutlar değişmedi; yukarıdaki canlı çalıştırma komutları aynen geçerli.

Commit yok, `env.sh` okunmadı, canlı çağrı yapılmadı.

## Fix 2 (review T-006, bulgular 2–4)

Hepsi `builder/extract.py` ve `builder/build.py`'de. `spec.py` ve `offer_check.py`'ye dokunulmadı; o dosyalarda Codex çalışıyor.

**Bulgu 2: tatiller ve gün sayıları artık hata ve onarım konusu.**

- **Tatil tarihleri:**
  - Her ISO tatil tarihi dokümanlarda yazılı bir tarihle eşleşmeli; eşleşmezse hata.
  - Karşılaştırmadan önce brief'teki tarihler normalleştiriliyor (`brief_dates`): ISO, `26 October 2026`, `26th of Oct`, `October 26, 2026`, `Oct 26` ve sayısal `26/10/2026` ya da `26.10.2026`. Sayısal tarihler gün-ay ve ay-gün olarak iki türlü okunuyor.
  - Yılsız yazılmış tarih ay-gün olarak eşleşiyor.
  - Eski "yıl geçiyorsa sessiz kal" kısayolu kaldırıldı.
- **Gün sayıları:** `earliest.days` ve `latest[].days` dokümanlarda rakam (`12`), sıra sayısı (`12th`) ya da kelime (`twelve`, `twelfth`) olarak geçmeli. 0 için `today` da kabul ediliyor.
  - Liste numaraları (`12.`) ve kural atıfları (`rule 30`, `rules 6, 47`) kanıt sayılmıyor. Aksi halde Brief A'da 1–47 arasındaki her sayı "yazılı" görünüyordu.

**Bulgu 3: outcome/reason çifti birlikte aranıyor.**

- Çift aynı tablo satırında ya da aynı cümlede geçmeli; geçmezse `pair X/Y not found together in the documents` hatası ve onarım. Reason boşsa outcome'un dokümanda geçmesi yeterli. Bu tek kontrol tablo satırlarına, özel yollara ve kapatan route değerlerine uygulanıyor.
- **Geliştirme sırasında bulduğum açık:**
  - İlk sürümde "satır + sonraki satır" penceresi kullanıyordum. Komşu tablo satırları ve ardışık kurallar yüzünden yanlış çiftleri kabul ediyordu (`not_reached/failed`, `transferred/dispute`).
  - Artık pencere tek satır. Bir satır yalnızca cümlesi bir sonraki satıra taşıyorsa (nokta, iki nokta ya da `|` ile bitmiyorsa ve sonraki satır yeni bir madde değilse) onunla birleştiriliyor.
  - İki durum için de test var.

**Bulgu 4: kapsama görünür oldu.**

- **Son satır uyarısı:** `unmapped > 0` ise build'in son çıktı satırı şu oluyor: `warning: N brief item(s) not mapped to the spec; see coverage_unmapped in traces/<slot>....log`.
  - `--validate` ve kaydetme modunda bu satır stdout'a gidiyor.
  - `--print` modunda stderr'in son satırına gidiyor, çünkü stdout workflow JSON'u ve komutlarınız onu dosyaya yönlendiriyor. Stdout'a yazılırsa JSON bozulurdu. İsterseniz `--print`'te de stdout yapılabilir.
- **Kapsama hataları türüne göre trace'e yazılıyor:** `coverage_error: purpose=coverage|coverage_followup kind=model_call|invalid_json|bad_shape|internal detail=…`.
  - `bad_shape` beklenen dizinin olmaması demek.
  - Kapsama hiç çalışmazsa her madde ayrıca `coverage_unmapped` satırı alıyor; spec'e `coverage.check = "not run"` yazılıyor.

**Doğrulama:** Canlı Brief A spec'i (`traces/t006-brief-a.spec.json`) yeni kontrollerden sıfır hatayla geçiyor. Bütün çiftler tablo satırlarında birlikte geçiyor, tatiller ISO, gün sayıları (12, 7, 0 = `today`) brief'te yazılı.

**Testler:** 139 testin hepsi geçiyor. Yeni veya değişen testler:

- tablo dışı çift (satırda ve özel yolda);
- iki tablo satırından birleştirilmiş çift için onarım;
- tabloda satırı olmayan route çifti;
- tatil ve gün sayısı kanıtı, hem ISO hem kelimeli tarihlerle (tarih silinince hata);
- `brief_dates` biçimleri;
- kapsama hata türleri (`invalid_json`, `bad_shape`, `model_call`);
- `--print`'te stdout'un saf JSON kalması ve son satır uyarısı.

**Koordinasyon notu:**

- Codex, fixture A'yı ve `tests/fixtures/extract/brief-a-replies.json`'ı yeni offer alanlarıyla güncelledi: `next_weekday`, `max_rejected_offers_by_product`. Testlerim güncel fixture'a göre geçiyor.
- **Öneri (yapılmadı):** Bu iki alan isteğe bağlı ve varsayılanı var; çıkarma kırılmıyor. Ama extraction prompt'u (`EXTRACT_OFFER_TASK`) onları henüz istemiyor, yani canlı çıkarmada varsayılanda kalırlar. Brief A'nın "next Friday" ve band başına deneme kuralları tam bu alanlara karşılık geliyor. Codex'in sözleşmesi kesinleşince prompt'a iki satır eklenmeli. Karşılaştırma aracı `offer` alanlarının hepsini zaten karşılaştırıyor; fark orada görünecek.

Commit yok, `env.sh` okunmadı, canlı çağrı yapılmadı.
