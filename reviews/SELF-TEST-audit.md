# SELF-TEST denetimi

**Tarih:** 2026-10-10  
**Kapsam:** [`docs/SELF-TEST.md`](../docs/SELF-TEST.md), kit v3 README/dokümanları, `run_cases.py`, mevcut builder CLI ve Adım 1'in gerçek offline koşusu  
**Kısıtlar:** Freya isteği, `--validate`, workflow kayıt/yayın, commit ve `env.sh` erişimi yapılmadı. Kod veya mevcut doküman değiştirilmedi.

## Sonuç

Planın ana sırası doğru: offline yapı kontrolü → chat → simülasyon → başarısızlık analizi → yeniden üretilebilirlik → teslim provası. Kitteki puanlama, 3/3 koşulu, iki final brief, 1–3 ürün, 30 dakika, export ve trace yükümlülükleriyle büyük ölçüde uyumlu.

Ancak plan şu haliyle uygulanmaya hazır değil. İki yüksek önem taşıyan sorun var:

1. Adım 1'de üretilen workflow'lar kitin prompt kurallarını gerçekten geçmiyor.
2. “Offline `--print`” ile mevcut T-006 durumu yanlış anlatılıyor; `--print` ancak `--spec` ile ağsızdır. Normal `--print` extraction modelini çağırır.

Sentetik `--print` adımı da repoda bulunan spec + kit OpenAPI ile doğrudan çalışmıyor.

## Bulgular — önem sırasıyla

### 1. [Yüksek] Üretilen workflow'lar kit prompt kurallarını geçmiyor

Kit [`workflow-format.md`](../build-the-builder-v2/docs/workflow-format.md) şunları zorunlu tutuyor:

- tool'suz conversation node, o turda tool çağrısına izin olmadığını açıkça söylemeli;
- tool'lu conversation node, tool'u tam adıyla anmalı ve ne zaman çağrılacağını söylemeli.

Üç üretilen JSON üzerinde bağımsız kontrol sonucu:

- A: 6 prompt ihlali;
- A+B: 7 prompt ihlali;
- sentetik: 6 prompt ihlali.

Ortak eksikler:

- `opening`, `opening_reask`, `negotiate`: açık “no tool call” kuralı yok;
- `third_party`: `schedule_callback` adı yok;
- `identity`: `verify_identity` adı yok;
- `confirm_record`: `create_promise` adı yok;
- A+B `special_product_dispute`: `add_note` adı yok.

Bu, bağlı [`reviews/KIT-V3-COMPLIANCE.md`](KIT-V3-COMPLIANCE.md) içindeki D-1/D-2 bulgularının hâlâ geçerli olduğunu doğruluyor. SELF-TEST kontrol listesi yalnız no-tool maddesini özetliyor; exact tool-name maddesini atlıyor.

**Önerilen düzeltme metni:**

> Her conversation node için iki yönlü prompt kapısı çalıştır: `tools` boşsa `task_message` ve varsa `loop_prompt`, bu turda hiçbir tool çağrısına izin verilmediğini açıkça söylemeli. `tools` doluysa her `function.name` prompt'ta birebir geçmeli ve çağrı koşulu yazılmalı. Bu kontrol başarısızsa Adım 1 başarısızdır; Freya testine geçme.

Builder için ayrı düzeltme gerekecek; bu denetimde kod değiştirilmedi.

### 2. [Yüksek] “Offline” ve T-006 anlatımı güncel değil

SELF-TEST, `--print` ve `unittest` işlemlerini offline/onaysız grup olarak anlatıyor ve Adım 2'de T-006'yı gelecekte yapılacak iş gibi gösteriyor. Oysa T-006 uygulanmış durumda:

- normal `python3 builder/build.py <brief> <openapi> --print`, Freya'ya gitmez fakat Anthropic extraction çağrıları yapar;
- yalnız `--print --spec <fixture>` tamamen ağsızdır;
- normal build/print için `ANTHROPIC_API_KEY` gerekir; ortam değişkenleri bölümü yalnız iki Freya/banka anahtarını listeliyor;
- `--single-step`, modelsiz eski fallback'tir.

CLI yardım metni de açıkça “spec extraction still calls the model unless `--spec`” diyor.

**Önerilen düzeltme metni:**

> `--print --spec <spec.json>` ağsız offline render'dır. `--print` tek başına Freya'ya istek göndermez, fakat brief extraction için Anthropic API'ye gider, `ANTHROPIC_API_KEY` gerektirir ve model maliyeti/süresi doğurur. Adım 1 fixture spec'lerle renderer'ı; Adım 2 ise gerçek extraction'ı test eder.

T-006 şart paragrafı da geçmiş zamanla güncellenmeli: extraction artık mevcut; test edilmesi gereken şey doğruluk, tekrar edilebilirlik ve süre.

### 3. [Yüksek] Extraction tekrar edilebilirliği için ölçülebilir kapı eksik

Adım 8 genel olarak builder'ı iki kez çalıştırmayı söylüyor, fakat T-006'nın kritik çıktısı olan `traces/<slot>.spec.json` için ayrı kabul ölçütü vermiyor. Temperature 0 olsa bile model alias'ı, coverage sınıflaması, repair yolları ve raw-material yorumları değişebilir. [`tasks/T-006-report.md`](../tasks/T-006-report.md) iki extraction spec'ini karşılaştıran komutları zaten veriyor; SELF-TEST bunları içermiyor.

**Önerilen düzeltme metni:**

> Temiz brief, A+B ve raw-material brief için extraction'ı en az iki kez ayrı slotlarda çalıştır. `tools/compare_spec.py` ile kimlik alanlarını/sırasını, offer takvim ve tablolarını, outcome tablosunu, special path'leri, `coverage.unmapped`, provenance ve override sonuçlarını karşılaştır. Her koşuda `extract_seconds`, çağrı sayısı, repair sayısı ve warning/unmapped sayısını kaydet. Anlam değiştiren fark veya 5 dakika extraction hedefinin aşılması başarısızlıktır.

Bu canlı extraction testi Freya istemez ama Anthropic ağına gider ve 30 dakikalık final bütçesinden pay yer.

### 4. [Orta-Yüksek] Sentetik `--print` adımı mevcut repo dosyalarıyla çalışmıyor

Şu gerçek komut başarısız oldu:

```text
python3 builder/build.py --print --spec tests/fixtures/spec-synthetic.json \
  build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json
```

Hata:

```text
outcomes are not in the close_call enum: escalated, settled, unfinished, unreached, unverified
```

Sentetik spec farklı outcome kodları kullanıyor, fakat repoda ona eşlik eden sentetik OpenAPI yok. Test kodu bunu bellekte kit enum'una değer ekleyerek çözüyor; SELF-TEST bu gizli yardımı söylemiyor. Denetimde `/private/tmp` altında enum'u eşleştirilmiş geçici OpenAPI ile tekrar çalıştırıldığında sentetik JSON üretildi.

**Önerilen düzeltme metni:**

> Sentetik spec, kendi outcome enum'larını taşıyan sentetik OpenAPI fixture'ı ile çalıştırılmalıdır: `--spec tests/fixtures/spec-synthetic.json ... tests/fixtures/openapi-synthetic.json`. Kit OpenAPI ile çalıştırılması beklenmemelidir.

Repo içinde böyle bir fixture oluşturulmayacaksa Adım 1'de sentetik komut kaldırılmalı veya geçici OpenAPI'nin nasıl türetileceği açıkça yazılmalı.

### 5. [Orta] Final Brief B komut şekli kesin bilgi gibi yazılmış

SELF-TEST, Brief B için “iki brief'i birden ver” diyor. Kit örnek builder'ı A+B alıyor; buna karşılık [`STARTER-KIT-FACTS.md`](../docs/STARTER-KIT-FACTS.md) final run contract'ını bir brief + bir tool API olarak kaydediyor ve bu farkı `[TO-CONFIRM]` bırakıyor. Dolayısıyla SELF-TEST belirsizliği kesinleştirmiş.

**Önerilen düzeltme metni:**

> Kit practice Brief B, A'nın eki olduğu için yerel provada A+B sırasıyla verilir. Final teslim komutunun her final brief için yalnız o brief + kendi OpenAPI'sini mi, yoksa birikimli dokümanları mı alacağı TO-CONFIRM'dir. Final talimatı geldiğinde aynı run contract birebir uygulanır; builder her iki giriş biçimiyle de prova edilir.

### 6. [Orta] Hang-up ve chat 5xx dayanıklılık adımları eksik

Plan normal chat ve simülasyonu kapsıyor, fakat iki gözlenmiş kritik davranış için açık test yok:

- müşteri görüşmenin farklı aşamalarında kapatınca end-of-call `close_call` tam bir kez çalışmalı;
- chat 502/503/504 yanıtı, tur işlenmiş olsa bile dönebiliyor. Körlemesine resend duplicate tool call üretebilir.

Bu riskler [`UAT-FINDINGS.md`](../docs/UAT-FINDINGS.md) F-012, F-023 ve F-031'de kayıtlı.

**Önerilen düzeltme metni:**

> Opening, identity, negotiation ve kapanış sonrası aşamalarda chat'i sonlandır; ledger'da tam bir `close_call` olduğunu doğrula. 502/503/504 alınırsa aynı mesajı hemen yeniden gönderme: önce call record/ledger'da turun ve tool çağrısının işlenip işlenmediğini kontrol et; işlenmemişse kısa beklemeden sonra yalnız bir kez retry et. Platform 5xx'lerini ayrı failure label ile kaydet.

### 7. [Orta] Farklı `now` testi var ama otomatik doğrulama planı zayıf

`run_cases.py --cases` gerçekten var. SELF-TEST'in case kopyalayıp `now` değiştirme önerisi teknik olarak çalışır; ancak beklenen ledger tarihlerini değiştirmeden “banka skoruna güvenme, elle bak” demek finaldeki birkaç takvim gününü yeterince taklit etmez.

**Önerilen düzeltme metni:**

> En az üç farklı `now` için ayrı sentetik case dosyası üret; beklenen söz tarihlerini ve tatil/hafta sonu sonuçlarını o tarihe göre önceden hesaplayıp case'in `expected` alanına yaz. Her tarih için today/tomorrow, next-week weekday, tatil, hafta sonu ve deadline sınırı vakalarını otomatik ledger assertion ile çalıştır.

### 8. [Orta] Brief B çok ürün kapsamı hedefli bir kapı değil

Plan `--brief B` ve stilleri çalıştırıyor; bu doğru. Fakat “Brief B geçti” ifadesi, tek/iki/üç ürün ve “hepsi/bazıları/farklı deadline” ailelerinin ayrı ayrı doğrulandığını garanti etmiyor.

**Önerilen düzeltme metni:**

> Brief B'de PUB-11, PUB-12 ve PUB-13'ü önce `--only` ile ayrı ayrı 3/3 çalıştır; ledger'da ürün başına doğru `product_id`, tutar, tarih, note/promise sayısı ve kapanış önceliğini doğrula. Sonra bütün B grubunu ve konuşma stillerini çalıştır.

### 9. [Orta] Workspace sınırı 200 diye kesin yazılmamalı

Kit README 200 workflow derken hackathon sayfası için kaydedilmiş değer 10. [`STARTER-KIT-FACTS.md`](../docs/STARTER-KIT-FACTS.md) bunu açık bir kaynak çatışması ve TO-CONFIRM olarak tutuyor. SELF-TEST yalnız 200 yazıyor.

**Önerilen düzeltme metni:**

> Workspace workflow sınırı kaynaklarda 10 ve 200 olarak çelişiyor; gerçek sınır TO-CONFIRM. Test stratejisi sınırdan bağımsız olarak aynı slotu yerinde güncellemeli ve yeni workflow oluşturmamalı.

### 10. [Orta-Düşük] Trace kontrol listesi kit yükümlülüğünü eksik özetliyor

Kit trace'i “Freya'da ne oluşturuldu” bilgisiyle ister. Proje facts'i bunu workflow/agent id ile birlikte node ve tool sayısı olarak somutlaştırıyor. SELF-TEST yalnız `workflow_id` ve `agent_id` diyor. Ayrıca normal extraction için Anthropic anahtarı da secret taramasına dahil edilmeli.

**Önerilen düzeltme metni:**

> Trace'te start/end UTC, toplam süre, her model çağrısının model/amaç/süre/token bilgisi, input hash'leri, extraction/repair/coverage özeti, workflow_id, agent_id, published version, node/global-node/tool sayısı, export yolu ve gerçekten koşulan self-test sonuçları bulunmalı. `fak_`, team key, `sk-ant-` ve bilinen bütün secret environment değerleri bulunmamalı.

### 11. [Düşük] “İlk 10 takım” ifadesi yerel doğrulanmış kaynakta desteklenmiyor

SELF-TEST “İlk 10 takım” diyor. Mevcut source-of-truth özeti yalnız “top teams” diyor; kit README bir sayı vermiyor. Resmi hackathon sayfası bu denetim ortamından açılamadığı için sayı bağımsız olarak doğrulanamadı.

**Önerilen düzeltme metni:**

> Üst sıralardaki takımların commit'i yeniden çalıştırılır ve trace/kod/ajan karşılaştırılır.

Sayı ancak resmi sayfadan yeniden doğrulanırsa eklenmeli.

### 12. [Düşük] Hardcode taraması için düz metin liste yanlış pozitif üretebilir

`promise`, `promise_recorded`, sabit yedi tool adı ve skeleton state'leri framework sözlüğüdür; brief sonucu değildir. Salt `rg` ile “sonuç kodu” aramak bunları sızıntı sanabilir. Mevcut AST tabanlı leakage testi OpenAPI değerlerini ve framework vocabulary'sini ayırıyor ve daha güvenilir.

**Önerilen düzeltme metni:**

> Önce AST tabanlı leakage testini çalıştır. Sonra pratik fixture'lardan tatil tarihleri, tutarlar, outcome/reason/note kodları, kimlik alanları ve banka adını çıkarıp `builder/*.py` string literal'larıyla karşılaştır; yalnız fixed tool adları, call variables ve açık framework allowlist'ini hariç tut. Her eşleşme dosya/satır ve allowlist gerekçesiyle raporlanmalı.

## Araç ve link doğrulaması

### `run_cases.py` seçenekleri

Kaynak ve gerçek `--help` çıktısında aşağıdakilerin tamamı var:

- positional `agent_id`;
- `--brief`;
- `--cases` — evet, gerçekten var; default `public-test-set.json`;
- `--out`;
- `--only`;
- `--reps`;
- `--style {asks_back,corrects,in_words,pieces,talkative}`;
- `--rerun-if-slow`.

SELF-TEST'teki seçenek adları doğrudur. `--brief` argparse seviyesinde A/B choices ile sınırlandırılmamış olsa da A ve B filtreleri pratik veriyle çalışır. `--rerun-if-slow`, yavaş koşu arasında 5 dakika beklediği için builder'ın 30 dakikalık kendi self-testine konmamalı; yalnız geliştirme testinde kullanılmalı.

### Linkler

SELF-TEST içindeki yerel Markdown linklerinin tüm hedefleri mevcut:

- `docs/EVALUATION-AND-TESTING.md`;
- `reviews/KIT-V3-COMPLIANCE.md`;
- `docs/UAT-FINDINGS.md`.

Ancak `KIT-V3-COMPLIANCE.md` T-006 öncesinden kalma: R-1/R-3 artık güncel değil, D-1/D-2 ise bu denetimde hâlâ doğrulandı. Bağlantı kırık değil ama belge kısmen stale; SELF-TEST güncel bir compliance kontrolüne bağlanmalı veya tarih/durum notu eklemeli.

Harici hackathon `#evaluation` bağlantısı bu denetim ortamındaki web aracıyla açılamadı. Bu nedenle resmi sayfa iddiaları kit README ve `STARTER-KIT-FACTS.md` üzerinden karşılaştırıldı.

## Adım 1 — gerçek çalışma sonuçları

### 1. Unit test

Komut:

```text
python3 -m unittest
```

Sonuç: **128/128 geçti**, 1.474 saniye.

### 2. `--print` üretimleri

Tamamen ağsız kalmak için üçünde de `--spec` kullanıldı.

| Üretim | Sonuç | Düğüm | Global | Tool |
|---|---:|---:|---:|---:|
| Brief A + `spec-brief-a.json` | geçti | 19 | 3 | 7 |
| Brief A+B + `spec-brief-b.json` | geçti | 21 | 3 | 7 |
| Sentetik spec + kit OpenAPI | **kaldı** | - | - | - |
| Sentetik spec + enum'u eşleştirilmiş geçici OpenAPI | geçti | 18 | 1 | 7 |

Üç başarılı print trace'i açıkça `freya: not contacted (--print)` ve `model_calls: none` yazıyor.

### 3. Üretilen JSON kontrol listesi

Üç başarılı JSON için geçen kontroller:

- hiçbir yerde `null` yok;
- top-level `agent_config` yok;
- passthrough node'lar `always` transition ile bitiyor;
- `tools` yalnız conversation node'larda;
- `pre_actions` yalnız code/api_request node'larda;
- bütün response mapping yolları `data.` ile başlıyor;
- boolean `true`/`True` çiftleri tam;
- code/default, pre-hook ve post-hook kaynaklarında `{{`/`}}` yok.

Kalan kontroller prompt bulguları nedeniyle başarısız:

- no-tool conversation açıklaması;
- tool'lu conversation prompt'unda exact function adı.

Bu yüzden Adım 1'in genel sonucu **başarısız** sayılmalıdır; unit testlerin yeşil olması tek başına kit uyumu değildir.

### 4. Hardcode taraması

Çalıştırılan explicit tarama şunları kapsadı:

- fixture tatil tarihleri;
- örnek tutarlar;
- `Freya Bank`;
- pratik kimlik alanları;
- outcome/reason/note kelimeleri.

Sonuç:

- tatil tarihleri, örnek tutarlar ve `Freya Bank` için `builder/` altında eşleşme yok;
- pratik kimlik alanları hardcode edilmemiş;
- bulunan `promise` benzeri eşleşmeler fixed tool/skeleton/spec vocabulary ve generic prompt metinleri; pratik brief outcome değeri sızıntısı değil;
- unit paketindeki AST tabanlı `test_builder_string_literals_do_not_embed_fixture_values` geçti.

Hardcode kapısı **geçti**.

## Eksik operasyon kapıları — kısa liste

Plan revize edilirken en az şu kabul kapıları görünür olmalı:

1. T-006 clean + raw-material extraction repeatability ve süre ölçümü.
2. Farklı `now` değerleriyle otomatik beklenen-ledger testleri.
3. Brief B bir/iki/üç ürün ve ürün başına tool-call doğrulaması.
4. Hang-up'ın farklı aşamalarda tam bir kez close üretmesi.
5. 502/503/504 sonrası ledger/call reconciliation; kör retry yok.
6. Her final brief için extraction + render + Freya doğrulama + kısa self-test dahil 30 dakikalık duvar saati kapısı.
7. Trace'te bütün model çağrıları, artifact kimlikleri/sayıları, input hash'leri, süre ve secret taraması.
8. Workspace limitinden bağımsız update-in-place doğrulaması.

## Nihai değerlendirme

SELF-TEST iyi bir iskelet, fakat önce bulgu 1–4 dokümanda ve ilgili builder davranışında kapatılmalı. Bugünkü Adım 1 sonucu: **unit/hardcode/yapısal JSON kontrolleri geçti; kit prompt uyumu ve sentetik testin tekrar üretilebilir komutu kaldı.** Freya aşamasına geçilmemeli.
