# T-006 review (spec'i brief'ten çıkarma: llm.py, extract.py, compare_spec.py)

Rapor: tasks/T-006-report.md. Kod değiştirmedim, Freya'ya ve Anthropic'e istek atmadım. 128 test geçiyor. CTO'nun canlı koşusunun bıraktığı `traces/t006-brief-a.failed.log` dosyasını okudum (aşağıda bulgu 1). Bulgu 1 için `docs/UAT-FINDINGS.md`'ye F-037 ekledim.

## Karar: düzeltme gerekli
Canlı koşu şu an bulgu 1 yüzünden duruyor: paralel çağrılarda sıcaklık (temperature) yedeği yarışıyor. Küçük düzeltme, ama bu olmadan extraction hiç çalışmaz. Bulgu 2 ve 3 hidden brief'te sessiz yanlış spec riskini azaltır, bulgu 1'den sonra yapılmalı. Anahtar yönetimi, hata yolu ve prompt'lar temiz.

## Bulgular

### 1. [Yüksek, CANLI KOŞUDA GÖZLENDİ] `llm.py` sıcaklık yedeği paralel çağrılarda yarışıyor
- Kanıt: `traces/t006-brief-a.failed.log`: `extract:opening_identity` başarılı (7.043 giriş / 8.277 çıkış token, 51,8 sn); `extract:flow` `HTTP 400: temperature is deprecated for this model` ile düştü; build `LLMError`, exit 1. TO-CONFIRM 1 böylece cevaplandı: `claude-sonnet-5-5` sıcaklığı reddediyor.
- Neden: `llm.py` `complete()` (≈ satır 111–118) yedeği `self._send_temperature` paylaşılan bayrağıyla yönetiyor: `if exc.code == 400 and self._send_temperature and "temperature" in detail`. Dört çağrı paralel çalışıyor; ilk 400'ü alan iş parçacığı bayrağı False yapıp yeniden deniyor, ikinci iş parçacığı kendi 400'ünü bir an sonra alınca bayrak zaten False olduğu için koşul tutmuyor ve hata yükseliyor.
- **Düzeltme (iki satırlık):** kararı istek başına ver: gönderilen yük `temperature` taşıyorsa ve hata mesajı `temperature` diyorsa, bayrağın değerine bakmadan o isteği sıcaklıksız yeniden gönder. Daha sağlamı: sıcaklık hiç gönderilmesin (model reddediyor; `--print` ve çıktı kararlılığı için `temperature` zaten garanti değil). Bu durumda `claude-sonnet-5-5` için tekrarlanabilirlik, kayıtlı doğrulama ve onarım turlarıyla sağlanıyor; raporun açık sorusu 5 (tarihli snapshot adı) bununla birlikte önem kazanıyor.
- İkinci küçük nokta aynı kodda: sıcaklık yedeği `attempt` sayacını tüketiyor (`continue` sonrası `attempt == 2`), yani sıcaklıksız ilk istek ağ hatası/5xx alırsa bir daha denenmiyor (`attempt == 1` koşulu). Yedek için ayrı döngü sayacı kullanın ya da sıcaklığı hiç göndermeyin.
- Not: yarışmayı yeniden üretmek için testi `Barrier` ile iki iş parçacığına aynı anda 400 dönen sahte opener ile yazın (mevcut testler tek iş parçacıklı).

### 2. [Orta] Tatil tarihleri yalnızca "uyarı", üstelik yıl eşleşmesiyle susturuluyor
- `extract.py` `check_spec_data` (≈ satır 646–648): `day not in check.brief and not check.in_brief(day[:4])` ise uyarı. Brief'te yıl (ör. `2026`) bir yerde geçiyorsa (örn. `now` değerinde) uydurulmuş veya yanlış yazılmış bir tatil tarihi hiç uyarı üretmiyor; uyarılar da hata değil. Tatil listesi takvim kontrolünü doğrudan belirler (bir tarihin yanlış olması söz tarihini yanlış kabul/ret ettirir, hepsi-ya-hiç).
- **Düzeltme:** ISO tarih brief'te yoksa **hata** (onarım turuna gitsin); brief tarihleri ISO dışı yazıyorsa (`26 October 2026`, `Oct 26`) önce brief'teki tüm tarihleri ISO'ya normalleştirip kıyaslayın (ay adı + gün + opsiyonel yıl). Aynı kontrolü `earliest/latest` günleri için de yapın: sayı brief'te bir metinde geçmiyorsa (`12th`, `12`, `twelfth`) uyarı yerine onarım. Brief A yalnızca ISO yazıyor, yani bugünkü fixture bunu yakalamaz; hidden brief'te çıkabilir.

### 3. [Orta] Outcome/reason çifti birlikte doğrulanmıyor
- `check.outcome_pair`: outcome ve reason her biri brief'te **veya** OpenAPI'de ayrı ayrı geçiyor mu diye bakıyor (`known_value`). `close_call` OpenAPI'sinde `reason` serbest string (enum yok; açıklaması "See the table in the brief"). Yani brief'in tablosunda bulunmayan bir çift (ör. `promise` ile bir reason, ya da var olan iki kelimenin yanlış eşlemesi) tüm kapıları geçer. Uydurma yalnızca "kelime bulundu" düzeyinde yakalanıyor.
- **Düzeltme:** çiftin brief'te **aynı satırda/tablo satırında** birlikte geçtiğini ara (`outcome` ve `reason` aynı satır ya da komşu iki satır). Bulunamazsa hata ve onarım: "Pair not found together in the documents". Reason'ı boş olan satırlar (`promise`, `paid`) için outcome'un tek başına geçmesi yeterli. Özel yol `outcome/reason` çiftleri için aynı kontrol.

### 4. [Düşük] Kapsama modelin kendi değerlendirmesi; yalnızca yolun varlığı doğrulanıyor
- `_coverage`: `covered` iddiası için en az bir `paths` girdisinin spec'te çözülmesi yeterli; yolun o maddeyi gerçekten karşıladığı doğrulanmıyor. Kapsama başarısız olursa ya da eksik kalırsa build devam ediyor; sonuç yalnızca trace'te (`coverage_unmapped`). Bilinçli tercih ve güvenli yönde (hepsini "doğrulanmadı" sayıyor, atlanan id'ler `missing`), bu yüzden düşük.
- Öneri: `unmapped > 0` ise build'in son satırında (stdout) tek satır uyarı basılsın; yoksa kimse trace'e bakmaz. Ayrıca kapsama çağrısı ve ek çağrı `except Exception` ile her hatayı yutuyor, anahtar sızıntısı yok ama `LLMError` türünden bir ağ hatası bile "coverage failed" olarak devam ediyor. Kabul, uyarı trace'te.

### 5. [Düşük] Diğer
- Zaman aşımı 300 sn; gözlenen en uzun çağrı 8.277 çıkış tokenı için 52 sn, yeterli. Kapsama çağrısı (186 madde) ~6k token bekleniyor, yeterli.
- Paralel çağrılarda `pool.map` bir iş parçacığının hatasını diğerleri bittikten sonra yükseltiyor; sonuç beklenen (hata, kısmi spec yok), yalnızca başarısız çağrıdan sonra kalan çağrılar tamamlanana kadar bekleniyor. Önbellek yazımı: ilk dört çağrı aynı bağlamı aynı anda yazıyor, onarım/kapsama çağrılarında `cache_read_tokens` görünmeli (rapor TO-CONFIRM 2).

## İstenen kontroller

| Kontrol | Sonuç |
|---|---|
| `llm.py` anahtarı hiçbir yere yazıyor mu / maskeleme | **Yazmıyor.** Anahtar yalnızca istek başlığında (`x-api-key`), her çağrıda `os.environ`'dan okunuyor. Doğruladım (sahte anahtar `topsecretvalue123XYZ` ve `sk-ant-…` ile): `TraceWriter.add`, `build._error_text`, `llm.redact` ve 401 yanıt gövdesinin hata mesajına girmesi dört yolda da `[REDACTED]`. `urllib.error.HTTPError` önce yakalanıyor (URLError alt sınıfı), hata gövdesi maskeleniyor ve 300 karakterle kesiliyor. Repo'da `sk-ant` yalnızca llm.py, run_trace.py, test ve rapor dosyasında (desen sabiti); trace dosyalarında yok. |
| Paralel çağrılar | Dört grup `ThreadPoolExecutor` ile paralel; ortak bağlam önbellek işaretli; onarım aynı konuşmanın devamı. **Bulgu 1** yüzünden şu an çalışmıyor. |
| Doğrulama/onarım kuralları | Kapsamlı: OpenAPI alan/enum doğrulaması (kimlik soru alanları tek enum'da, boolean/integer tipleri, ürün dizisi ve id alanı, söz ve kapanış alanları), outcome `close_call` enum'unda, mükerrer satır, zorunlu bitiş durumlarının eşlenmesi, kapatan route değerlerinin çiftinin tabloda olması, özel yol araç/alan/enum kontrolü, `overrides` (eski metne atıf hata), `parse_spec` ve kuru render son kapı. Boşluklar: bulgu 2 (tarihler) ve bulgu 3 (çift birlikteliği). En fazla 2 onarım turu, hâlâ hata varsa `ExtractionError`. |
| Kapsama yöntemi | Bulgu 4. Maddeler kodla bölünüyor (186), model `covered/not_relevant/missing` diyor, kod yolun varlığını kontrol ediyor, eksikler için tek hedefli tekrar sorma, bozan ekleme atılıyor. Makul ve güvenli. |
| Prompt'larda brief değeri | **Yok.** `extract.py`, `llm.py` ve 10 extraction prompt'unu (prompts.py, PROMPTS.md) brief'lerden ve fixture'lardan çıkardığım jetonlarla taradım (banka adı, ürün tipleri, outcome/reason adları, sayılar, saatler, tarih, müşteri adları): hiçbiri yok. Prompt'lar spec alanlarını ve koleksiyon alanını anlatıyor; özel yol örnekleri ("ödeme zaten yapıldı", "borcu reddetme", "zorluk", "farklı plan", "insan") alan düzeyinde genel kategoriler, değer taşımıyor; yine de yeni bir brief'te bu örnekler modeli yönlendirebilir, izlenmeli. Sızıntı testi ve yeni prompt testi yeşil. |
| Hata yolunda sessiz kısmi ajan | **Oluşmuyor.** Çıkarma Freya'dan önce; `ExtractionError` (SpecError) → exit 2, `spec.json` yazılmıyor, `spec.failed.json` ve `extract_error` satırları yazılıyor; `LLMError` (bulgu 1'deki durum) → exit 1, `failed.log`. İkisinde de doğrulama/kaydetme çağrılmıyor. |
| `build.py` `--spec` olmadan extraction | **Evet.** `--spec`, `--single-step` karşılıklı dışlayıcı; ikisi de yoksa `_extract` çağrılıyor, sonra normal build. `--print` model çağırıyor (yardım metni bunu söylüyor). `--single-step` eski ajan. |
| `tools/compare_spec.py` | Anlamlı alanları karşılaştırıyor: kimlik alanları ve sırası, route sayıları, kapanış çiftleri (değer adı yok sayılarak), tool alanları, limitler, offer'ın tüm veri alanları ve tatiller, outcome tablosu (satırlar, durum eşlemesi, `wins_over_promise`, zorunlu cümleler), özel yollar (araç, sabit argüman, `then`, `available_in`, `ask`). Bilinçli olarak kural metinlerini, `answer_format`, `agent.introduction` ve `global_rules` içeriğini karşılaştırmıyor (kelime yok sayma kararı); canlı koşuda bu alanlara insan gözüyle bakılmalı. |

## Kurallara uyum
Freya isteği yok, stdlib (`urllib`, `concurrent.futures`), Python 3.10+. Testler çevrimdışı. Trace'te model çağrısı başına model, amaç, token ve süre var (yarışma kuralı). Anahtar `env.sh`'tan okunmuyor, ortam değişkeninden.

## Düzeltme sonrası bakılacaklar
1. Bulgu 1 kapanınca Brief A canlı koşusunu tekrarla: `extract_seconds`, `cache_read_tokens`, `extract_warning` sayısı ve `compare_spec` çıktısı.
2. İkinci koşu ile ilk koşuyu `compare_spec`'le karşılaştır (tekrarlanabilirlik; sıcaklık gitti, farklar beklenebilir, kritik alanlar aynı kalmalı).
3. Brief B (iki doküman) ve ayrıca ISO olmayan tarih biçimli bir sentetik brief ile tatil/gün sayısı kontrolleri.

---

# Fix kontrolü (T-006 Fix, Fix 2: bulgu 1–4)

Kod değiştirmedim, Anthropic ve Freya'ya istek atmadım. `python3 -m unittest`: 140 test geçiyor. Yalnızca `llm.py`, `extract.py`, `build.py` değişikliklerine baktım; Codex'in spec.py/offer_check.py/workflow.py işleri dahil değil.

## Karar: merge edilebilir
Bulgu 1 ve 4 kapandı, bulgu 2'nin tatil kısmı kapandı, bulgu 3 büyük ölçüde kapandı. İki kalan zayıflık (gün sayısı kanıtı ve çok çiftli satırlarda çapraz çift) hidden brief'te sessiz yanlışı tamamen engellemiyor; bir sonraki küçük işte sıkılaştırılmalı, ama bugünkü haliyle gerçek tablo çiftlerini hiç reddetmiyor ve en riskli boşluk (tarih) kapanmış durumda.

## Bulgu 1 (temperature yarışı): kapandı
- `llm.py`: karar artık o isteğin kendi payload'ına bağlı (`"temperature" in payload and "temperature" in detail`), paylaşılan ayar kilit altında; sıcaklık varsayılan olarak hiç gönderilmiyor (`EXTRACTION_TEMPERATURE = None`), trace'e `model_settings` satırı yazılıyor. Yeniden gönderme ağ hatası hakkını tüketmiyor (`attempt -= 1`).
- Kendi yarış testim: 4 iş parçacığı bariyerde aynı anda 400 aldı (sahte opener); dördü de sıcaklıksız yeniden gönderildi ve başarıyla döndü (8 istek: 4 sıcaklıklı, 4 sıcaklıksız). Önceki koddaki hata bu senaryoda ikinci çağrıyı düşürüyordu.

## Bulgu 2 (tatil tarihleri, gün sayıları)
**Tatil tarihleri: kapandı.** Brief tarihleri normalleştiriliyor (`brief_dates`) ve her ISO tatil tarihi dokümanda yazılı bir tarihle eşleşmek zorunda; yıl kısayolu kaldırıldı. Kendim denedim:
- Brief A: 5 gerçek tatil (2026-10-26, 11-11, 11-26, 12-25, 2027-01-01) kabul; uydurma 2026-10-27, 12-24, 11-12, 2027-01-02 **reddedildi**.
- Biçimler: `26 October 2026`, `11 Nov 2026`, `October 26, 2026`, `Oct 26th, 2026`, `26/10/2026` ve `10/26/2026` (iki yönlü okuma), `26.10.2026`, yılsız `the 26th of October` ve `Dec 25`, `may 5`/`5 may` hepsi doğru eşleşti.
- Küçük not: yılsız `(ay, gün)` eşleşmesi her yıl için geçerli ve "may" fiili bir sayıdan önce gelirse sahte tarih üretebilir (A için `(5, 2)` çıktı); zararsız, çünkü yalnızca kabul tarafını genişletiyor.

**Gün sayıları: kısmen kapandı.** Liste numaraları ve `rule N` / `rules 6, 47` atıfları sayılmıyor (denedim: yalnızca bu iki biçimi içeren metinde hiçbir sayı kabul edilmedi). Ama kanıt metindeki *her* rakamı sayıyor, gün bağlamı aramıyor. Brief A'da 0–12 arasındaki **tüm** sayılar ile 19, 25, 26, 45 kabul ediliyor (`1 to 7`, `8 to 45` bantları, `10:00`/`19:00` saatleri, tarihler, saatler yüzünden). Yani modelin yanlışlıkla yazacağı `earliest.days = 9` veya `latest.days = 5` brief'te geçmeyen bir değer olduğu halde "yazılı" sayılıyor; yalnızca 13–18, 20+ gibi hiç geçmeyen sayılar yakalanıyor.
- **Düzeltme (küçük):** sayıyı yalnızca bir gün birimiyle birlikte ara: `<sayı|ordinal|kelime> [business|calendar|working] day(s)` ve `today`/`same day`; band ve saat sayıları dışarıda kalır. Brief A'da 12, 7 ve 0 geçer (`12th business day`, `7th business day`, `today`), 9 geçmez.

## Bulgu 3 (outcome/reason çifti): büyük ölçüde kapandı
Tek satır (devam eden cümle varsa sonraki satırla birleşik) penceresiyle Brief A ve A+B için outcome × reason çaprazını kendim çalıştırdım:
- **Gerçek tablo çiftleri:** A'nın tablosundaki 14 çiftin (transferred: restructuring/human/support; no_promise: refused/hardship/dispute/service_error; not_verified: failed/declined; not_reached: callback/no_callback/wrong_number/deceased/unclear) **hepsi kabul**, hiçbiri reddedilmiyor (hem A hem A+B).
- **Komşu satır sızıntısı kapanmış:** raporun bahsettiği `not_reached/failed` ve `transferred/dispute` artık kabul edilmiyor; `not_reached/failed`, `transferred/dispute`, `not_verified/dispute` vb. reddedildi.
- **Kalan zayıflıklar (çapraz çift):** aynı satırda iki çift taşıyan kurallardan ve "paid"/"promise" gibi sıradan sözcüklerden dolayı şu yanlış çiftler hâlâ kabul ediliyor: `no_promise/declined`, `not_verified/refused` (kural 45'in tek satırı), `no_promise/support`, `transferred/hardship` (kural 32), `no_promise/paid`, `paid/dispute` (kural 40'ta "paid off"), ve `promise/<herhangi bir reason>` (çünkü "promise" her yerde geçiyor). Gerçek bir çifti kaçıran yok, ama modelin uydurduğu çapraz çift tek satır penceresinden geçebilir.
- **Düzeltme (küçük):** (a) tabloda "none" yazan veya reason'ı olmayan outcome'lar (`promise`, `paid`) için boş olmayan reason'ı doğrudan reddet; (b) satırda `` `outcome` / `reason` `` (eğik çizgi bitişik) kalıbı varsa yalnızca o bitişik çifti, tablo satırında ise "outcome sütunu | reason listesi" yapısını (tablo satırı) kabul et; düz cümlede çapraz kabul etme.

## Bulgu 4 (kapsama görünürlüğü): kapandı
`unmapped > 0` ise son çıktı satırı uyarı; `--print` modunda stdout'u bozmamak için stderr'e gidiyor (doğru, stdout workflow JSON'u); kapsama hataları türüne göre (`model_call`, `invalid_json`, `bad_shape`, `internal`) trace'e yazılıyor, hiç çalışmazsa her madde `coverage_unmapped` ve spec'e `coverage.check = "not run"`. Testleri var ve geçiyor.

## Ek gözlem (CTO'nun canlı Brief A koşusu, `traces/t006-brief-a.spec.json`)
- Spec üretilmiş; `compare_spec` 34 fark, 0 unmapped. Farkların büyük kısmı fixture'ın eksik olmasından (fixture'da 1 kural/bölüm, yeni spec'te 5–16) ve `say` cümlelerinden. Gerçek davranış farkları: `human` özel yolu `available_in` içinde `opening` var (A kural 42 "önce ve sonra" der: doğru, fixture eksik), `not_verified/declined` için `opening` kapanış satırı ve `offer_limit → no_promise/refused` farkı. Bu spec'ten üretilen workflow'da `special_human_request` ve `special_no_talk_unverified` global node'ları artık `opening` **ve** `opening_reask` içinde kullanılabilir (T-005d bulgusu kapanmış görünüyor).
- Ayrıntılı değerlendirme (`say` cümleleri, yeni özel yol seti) bu review'un kapsamı dışında; ilk Freya chat testi öncesi bir kez ayrıca bakılmalı.

## Kurallara uyum
Anahtar yönetimi değişmedi (önceki turda doğrulanmıştı). Freya isteği yok, stdlib, testler çevrimdışı.
