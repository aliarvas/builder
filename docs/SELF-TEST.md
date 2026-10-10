# Self-test: organizatör gibi test etmek

Bu doküman, builder'ı organizatörün final testine benzer şekilde nasıl test edeceğimizi anlatır: hangi araçları kullanacağımızı, hangi sırayla ilerleyeceğimizi, neye dikkat edeceğimizi. Pratik test verisi kitte hazırdır (`build-the-builder-v2/public-test-set.json`); farklı `now` ve görülmemiş brief provaları için üretilen sentetik veriler yalnız `tests/` altında tutulur, `builder/` içine girmez.

Kaynaklar: hackathon sayfası (https://www.freyavoice.ai/hackathon#evaluation), `build-the-builder-v2/README.md`, `build-the-builder-v2/docs/`. Genel test kuralları [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md) dosyasındadır; bu dosya onu adım adım uygular.

## Organizatör ne yapıyor (bizim taklit ettiğimiz şey)

- **Final briefleri:** İki gizli brief, her biri 30 müşteri; toplam 60. Briefin biri temiz bir spesifikasyon, diğeri ham banka malzemesi.
- **Müşteriler:** 1 ile 3 arası ürün. Birkaç farklı takvim gününe dağılmış. İnsan gibi konuşuyorlar.
- **Tekrar:** Her müşteri 3 kez koşulur. Üçü de geçerse müşteri geçmiş sayılır.
- **Üç kontrol:** Outcome (banka kayıtları), Policy (judge modeli), Honesty (judge modeli). Kısmi puan yok. Doğru bir ret de geçer; örneğin müşteri borca itiraz eder ve hiç söz kaydedilmezse.
- **Skor:** Geçen müşteri / 60. Eşitlikte sırasıyla: geçen müşterilerdeki toplam söz tutarı, trace'teki toplam build süresi, teslim zamanı.
- **Doğrulama:** Üst sıralardaki takımların commit'i klonlanır ve builder yeniden çalıştırılır. Sonuç trace ile karşılaştırılır. Bir reviewer agent trace, kod ve ajanları karşılaştırır. Yeniden çalıştırmada skoru belirgin düşen takım elenir.

## Araçlar

| Araç | Ne için |
|---|---|
| `python3 builder/build.py {brief} {tool_api}` | Resmi teslim koşusunda ek bayrak kullanma; geliştirme provalarında kanıtları ayırmak için `--slot` kullanılabilir |
| `python3 builder/build.py --print ...` | Freya'ya gitmeden workflow JSON'unu üretir; `--spec` yoksa extraction modeli çağrılır ve offline değildir |
| `python3 builder/build.py --print --spec <spec.json> ...` | Model ve Freya çağrısı olmadan fixture spec'ten workflow üretir; offline yapı kontrolü için |
| `python3 builder/build.py --validate ...` | Freya dry run. Kaydetmeden şemayı doğrular |
| `python3 -m unittest` | Offline birim testleri |
| `POST /api/v2/chat/message` | Tek tek chat turu. Hızlı ilk kontrol (api.md) |
| `build-the-builder-v2/tools/run_cases.py <agent_id>` | Pratik müşterileriyle simülasyon. Banka kaydı ve judge ile puanlar |
| `run_cases.py` seçenekleri | `--brief A\|B`, `--only PUB-03,...`, `--reps 3`, `--style pieces\|corrects\|talkative\|asks_back\|in_words`, `--out results/run.json`; `--rerun-if-slow N` en fazla N yavaş-koşu tekrarı yapar ve her tekrardan önce 5 dakika bekler |
| `freya.get_call(call_id)["messages"]` | Başarısız bir görüşmenin tam kaydı. `route_evaluated` olayı bir geçişin neden çalışıp çalışmadığını gösterir |
| `freya.export_workflow(workflow_id, path)` | Teslim edilecek dosya. Puanlanan şey bu dosya |
| `python3 tools/submission_check.py <trace> <export> --spec <spec>` | Trace, export, süre, kimlik/sayı eşleşmesi ve secret kontrolünü offline yapar |

**Ortam değişkenleri:** Normal extraction için `ANTHROPIC_API_KEY`; Freya adımları için `FREYA_API_KEY`; pratik ledger için `FREYA_BANK_TEAM_KEY` gerekir. `FREYA_BANK_TEAM_KEY` kendi seçtiğimiz, her seferinde aynı olan bir anahtardır. `--print --spec` ve `unittest` bunların hiçbirini gerektirmez.

**Onay kuralı:** `unittest`, `--print --spec` ve `submission_check.py` offline'dır. Normal `--print` Freya'ya gitmez fakat Anthropic extraction çağrısı yapar. Kayıt, dry run, normal build'in kayıt sonrası self-test'i, elle chat ve simülasyon Freya'ya istek atar; bunların her biri için önce kullanıcı onayı alınır (`AGENTS.md`, madde 6).

## Adımlar

### Adım 1. Offline kontroller (onay gerekmez)

1. `python3 -m unittest` çalıştır; hepsi geçmeli.
2. Ağsız kalmak için üç workflow'u fixture spec'lerle üret:

   ```text
   python3 builder/build.py --print --spec tests/fixtures/spec-brief-a.json --slot selftest-a \
     build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json \
     > /tmp/selftest-a.workflow.json

   python3 builder/build.py --print --spec tests/fixtures/spec-brief-b.json --slot selftest-ab \
     build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/briefs/brief-b.md \
     build-the-builder-v2/tools/openapi.json > /tmp/selftest-ab.workflow.json

   python3 builder/build.py --print --spec tests/fixtures/spec-synthetic.json --slot selftest-synthetic \
     build-the-builder-v2/briefs/brief-a.md tests/fixtures/openapi-synthetic.json \
     > /tmp/selftest-synthetic.workflow.json
   ```

   Workflow JSON stdout'a, yukarıdaki komutlarda `/tmp/selftest-*.workflow.json` dosyalarına gider; trace'ler `traces/selftest-a.print.log`, `traces/selftest-ab.print.log` ve `traces/selftest-synthetic.print.log` olur. Sentetik spec'i kit OpenAPI ile eşleştirme.
3. Üretilen JSON'u kit dokümanlarındaki kurallara karşı kontrol et. [`reviews/KIT-V3-COMPLIANCE.md`](../reviews/KIT-V3-COMPLIANCE.md) tarihsel incelemedir; güncel kapı aşağıdaki maddeler ve bunları uygulayan unit testlerdir:
   - `null` yok, `agent_config` yok.
   - Passthrough düğümleri `always` geçişiyle biter.
   - `tools` sadece konuşma düğümlerinde, `pre_actions` sadece code ve api düğümlerinde.
   - Mapping yolları `data.` ile başlar.
   - Boolean karşılaştırmalar `"true"` ve `"True"` ile, iki yazımla da yapılır.
   - Code içinde `{{` ya da `}}` yok.
   - Her conversation node için iki yönlü prompt kuralı geçer: `tools` boşsa `task_message` ve varsa `loop_prompt` bu turda tool çağrısına izin olmadığını açıkça söyler; `tools` doluysa her `function.name` prompt'ta birebir geçer ve ne zaman çağrılacağı yazılıdır. Bu kapı kalırsa Freya testine geçme.
4. **Hardcode taraması:** Önce `python3 -m unittest` içindeki AST tabanlı brief-literal leak testinin geçtiğini doğrula. Sonra fixture'lardan tatil tarihleri, tutarlar, outcome/reason/note kodları, kimlik alanları ve banka adlarını çıkarıp `builder/*.py` string literal'larıyla karşılaştır. Bulunmaması gerekenler:
   - tatil tarihleri, tutarlar, limitler,
   - sonuç ve not kodları,
   - kimlik soruları,
   - "Freya Bank" adı.

   Sabit yedi tool adı, call variable'lar ve açık framework vocabulary (`promise` gibi iskelet terimleri) brief sızıntısı değildir; her istisnanın allowlist gerekçesi olmalı. Diğer her eşleşmeyi dosya/satırla incele.

### Adım 2. Görülmemiş brief provası (en önemli adım)

Organizatör bizim görmediğimiz bir brief verecek. Bunu taklit et:

1. **Ham malzeme versiyonu:** Brief A'yı ham malzeme haline getir: mail, politika parçası, kuralı değiştiren bir not, kod listesi. Builder bütün parçaları ve sonraki override'ı doğru birleştiren ajanı üretmeli.
2. **Kural değişikliği versiyonu:** Brief A'nın sayılarını, kimlik sorularını, sonuç tablosunu ve takvimini değiştir.
3. **Farklı OpenAPI:** Tool adları aynı kalsın, alanları ve izin verilen değerleri (enum) değiştir. Builder alanları dosyadan okumalı.

Bu dosyalar test verisidir; `tests/` altında durur, `builder/` altına girmez. Builder hata vermeden, elle adım olmadan, 30 dakika içinde bitmeli.

T-006 extraction artık mevcuttur. `--spec` ile Adım 1 yalnız renderer'ı sınar; bu adım gerçek extraction doğruluğunu, tekrar edilebilirliğini ve süresini sınar. Temiz Brief A, A+B ve `tests/briefs/raw-a/` için extraction'ı en az iki kez farklı `--slot` adlarıyla çalıştır; böylece trace ve spec kanıtları birbirinin üstüne yazılmaz. `tools/compare_spec.py <extracted.json> <reference.json>` kimlik alanlarını/sırasını, route davranışını, outcome tablosunu, offer kuralları/takvimi, special path'leri, tool alanlarını, limitleri ve gerekli kapanış/özel-yol cümlelerini davranış değerleri üzerinden karşılaştırır; `coverage.unmapped` listesini ayrıca raporlar. Override sonucu ilgili değerin değişmesiyle görünür; provenance ve `overrides` kanıtını spec içindeki `source`/`overrides` alanlarını okuyarak ayrıca kontrol et. Araç wording ve provenance'ı bilerek karşılaştırmaz; fark varsa çıkış kodu 1'dir. Her koşuda `extract_seconds`, model çağrısı ve repair sayısı ile warning/unmapped sayısını kaydet. Anlam değiştiren fark veya 5 dakikalık extraction hedefinin aşılması başarısızlıktır; 30 dakika kesin build sınırıdır. `tests/briefs/README.md` güncel raw/changed brief komutlarını içerir.

### Adım 3. Resmi komutla build (onay gerekir)

1. `python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json`
2. Yerel kit provasında Brief B, Brief A'nın eki olduğu için `brief-a.md brief-b.md openapi.json` sırasını kullan. Final teslim komutunun yalnız final brief + kendi OpenAPI'sini mi, yoksa birikimli dokümanları mı alacağı `[TO-CONFIRM]`dir; final talimatını birebir uygula ve builder'ı önceden iki giriş biçimiyle de prova et.
3. Kontrol et:
   - **Süre:** 30 dakikanın altında mı? Bu süreye builder'ın kendi self-testleri de dahil.
   - **Workflow:** Aynı slot yerinde mi güncellendi? Yeni workflow açılmamalı. Workspace sınırı kaynaklarda 10 ve 200 olarak çelişiyor; gerçek değer `[TO-CONFIRM]`, update-in-place kuralı sınırdan bağımsızdır.
   - **Yayın:** Son versiyon yayınlandı mı (`isPublished`)? Yayınlanmamış bir versiyon simülasyonda kullanılmaz.
   - **Export:** `submission/<slot>.workflow.json` dosyası oluştu mu?

Bayraksız resmi koşuda `<slot>`, brief dosya adından türetilir (`brief-a.md` için `brief-a`; birden fazla brief'in stem'i `+` ile birleşir). Geliştirme provalarında `--slot <benzersiz-ad>` yalnız artifact/trace adını ve güncellenecek sabit workflow slotunu ayırmak için kullanılabilir; teslimde kaydedilecek tam `run_command` resmi bayraksız komut olmalıdır.

### Adım 4. Trace kontrolü (reviewer agent gibi oku)

Trace'te şunlar olmalı:

- başlangıç/bitiş UTC ve `total_duration_seconds`,
- her input'un SHA-256 özeti,
- her model çağrısının model, amaç, süre ve token bilgisi; toplam `extract_seconds`, repair/coverage ve warning/unmapped özeti,
- Freya'daki `workflow_id`, `agent_id`, `published_version`, node/global-node/toplam step/tool sayıları ve export yolu,
- builder'ın gerçekten yaptığı her `self_test` ve `self_test_summary` sonucu,
- son `status`.

Ayrıca:

- **Secret olmamalı.** `fak_`, `sk-ant-`, team key, `Authorization`, `x-api-key` ve bilinen secret environment değerleri trace/export/spec'e girmemeli.
- **Trace kod ve ajanla uyumlu olmalı.** Reviewer agent ikisini karşılaştıracak. Trace "self-test yapıldı" diyorsa, kodda da gerçekten o test olmalı.
- **Otomatik kapı:** Anahtarlar ortamda yüklüyken `python3 tools/submission_check.py traces/<slot>.log submission/<slot>.workflow.json --spec traces/<slot>.spec.json --verify-inputs --require-env` çalıştır; bütün zorunlu kontroller `PASS` olmalı. `WARN` satırlarını teslimden önce incele.

### Adım 5. Chat testi (onay gerekir)

1. Önce kitteki bank mock üzerinde pratik oturumu oluştur: `POST /v1/practice/sessions` gövdesine `{"case":"PUB-…"}` gönder ve `x-team-key: $FREYA_BANK_TEAM_KEY` başlığını kullan. Yanıttaki `variables` nesnesinin tamamı chat'in `customerVariables` değeridir; ledger için kullanılacak `customer_id` de bu nesneden gelir. Host ve route, [`STARTER-KIT-FACTS.md`](STARTER-KIT-FACTS.md) içindeki “Bank practice ledger” satırı ve `build-the-builder-v2/tools/score.py` ile aynıdır.
2. İlk turu `POST /api/v2/chat/message` ile `workflowId`, mesaj ve bu `customerVariables` nesnesini göndererek başlat; yanıttaki `callId`'yi sonraki her turda tekrar kullan. Böylece `now` dahil bütün case değişkenleri oturumdan gelir.
3. Ajan konuşmayı başlatıyor mu, tool çağırıyor mu, tool'dan sonra konuşuyor mu, bak.
4. Opening, identity, negotiation ve kapanış sonrası için ayrı pratik oturum/call oluştur; hedef aşamada `POST /api/v2/chat/end {"callId":"…"}` gönder. Sonra `GET /v1/practice/ledger/{customer_id}` çağrısını aynı `x-team-key` başlığıyla okuyup `calls` içinde `close_call`'un tam bir kez çalıştığını doğrula.
5. Chat 502/503/504 dönerse aynı mesajı körlemesine yeniden gönderme. Önce `GET /api/v2/call/{callId}` ve aynı ledger kaydında turun/tool çağrısının işlenip işlenmediğine bak; işlenmemişse kısa beklemeden sonra yalnız bir kontrollü retry yap. Platform hatasını ürün hatasından ayrı etiketle.
6. Bulunan her hatayı [`UAT-FINDINGS.md`](UAT-FINDINGS.md) dosyasına yaz: belirti, kök neden, çözüm, durum.

Chat geçmeden simülasyona geçme.

### Adım 6. Simülasyon: önce tek tur, sonra final koşulları (onay gerekir)

1. **Tek tur:** `run_cases.py <agent_id> --brief A` ve `--brief B`. Bu sadece ilk sinyal; tek yeşil sonuç kanıt değildir.
2. **Brief B ürün kapısı:** PUB-11, PUB-12 ve PUB-13'ü önce `--only` ile ayrı ayrı `--reps 3` çalıştır. Ledger'da ürün başına doğru `product_id`, tutar, tarih, note/promise sayısı ve kapanış önceliğini doğrula; sonra bütün B grubuna geç.
3. **3 tekrar:** `--reps 3`. Bir müşteri, üç çalıştırmanın üçü de geçerse sayılır. Final de böyle sayıyor.
4. **Konuşma tarzları:** Her tarzla ayrı koş: `pieces`, `corrects`, `talkative`, `asks_back`, `in_words`. Final müşterileri bunların karışımı gibi konuşur.
5. **Hata enjeksiyonu:** PUB-10'da `create_promise` ilk denemede başarısız olur. Ajan dürüst kalmalı ve tekrar denemeyi doğru yapmalı.
6. Her koşuda `--out results/<tarih>-<koşu>.json` ile call id'leri sakla.

**Süre:** Bir simülasyon bir seferde çalışır; ikinci `run_cases.py` birincisini bekler. 10 müşteri 3 ile 11 dakika sürer, `--reps 3` ve beş tarz ile toplam saatler sürebilir. Sırayı ve süreyi önceden planla.

### Adım 7. Başarısız müşteriyi analiz et

1. `run_cases.py` çıktısında kontrolün hangisinin kaldığına bak: banka kaydı mı, judge mı?
2. `freya.get_call(call_id)["messages"]` ile görüşmeyi oku. `route_evaluated`, `function_call_start` ve `function_call_complete` olaylarına, `variable_table`'a bak.
3. Kök nedeni builder'da düzelt; ajanı asla elle düzeltme. Sonra yeniden build et.
4. Bulguyu `UAT-FINDINGS.md` dosyasına yaz.

### Adım 8. Yeniden üretilebilirlik (üst sıra doğrulaması)

1. Temiz bir checkout'tan builder'ı aynı brief ile ikinci kez çalıştır.
2. İki çalıştırmanın farklı slotlardaki spec dosyalarını `python3 tools/compare_spec.py traces/<ilk-slot>.spec.json traces/<ikinci-slot>.spec.json` ile karşılaştır; ikinci koşu burada referanstır ve davranış farkında araç 1 döner. Kimlik, route, outcome, offer, special path, tool alanı, limit ve gerekli cümle farklarını araçtan; `coverage.unmapped` çıktısını rapordan; provenance/override farklarını iki spec'in `source`/`overrides` alanlarını okuyarak kontrol et.
3. İki çalıştırmanın skorlarını, trace'lerini, model/repair çağrı sayılarını, warning/unmapped sayılarını ve `extract_seconds` değerlerini karşılaştır. Skor belirgin düşüyorsa organizatör de aynısını görür ve takımı eler.
4. Çalıştırmalar arası anlam farkı veya büyük süre farkı varsa sebebini bul: LLM çıktısının değişkenliği, model alias'ı, coverage/repair yolu ya da zamana bağlı bir değer.

### Adım 9. Teslim provası

1. Her brief için ajan dosyası (`export_workflow`), aynı koşuya ait trace ve commit hazır olmalı; üretilen spec'i yeniden üretilebilirlik kanıtı olarak sakla.
2. `tools/submission_check.py` zorunlu kontrolleri geçmeli; trace/export/spec'te anahtar olmamalı.
3. Ajan dosyası builder'ın o çalıştırmasından gelmeli; elle düzeltilmiş olmamalı.
4. Form için `team`, `repo`, `commit`, tam `run_command`, brief başına `workflows` ve `traces` yolları hazır olmalı.

## Dikkat edilecekler

- **Puan yüzdesi değil, 3/3 önemli.** Çoğu zaman doğru olan bir ajan, finalde doğru sayılmaz.
- **Önce kontrol, sonra konuşma kalitesi.** Banka kaydı ve judge kontrolleri, akıcı konuşmadan önce gelir.
- **Dürüstlük.** Tool başarısızsa ajan asla "kaydettim" dememeli. PUB-10 bu senaryoyu test eder.
- **Takvim günleri.** Tüm pratik müşterilerinde `now` aynı: `2026-10-14T11:00`. Final ise birkaç farklı günde koşuyor.
  - Ajanın "bugün" bilgisini `now` call değişkeninden aldığından emin ol, `system.*` tarihlerinden değil.
  - En az üç farklı `now` için sentetik case dosyaları üret ve `--cases` ile ver. Her kopyada beklenen söz tarihlerini ve tatil/hafta sonu sonucunu önceden hesaplayıp `expected` alanını da güncelle.
  - Her tarih grubunda today/tomorrow, next-week weekday, tatil, hafta sonu ve deadline sınırını otomatik ledger assertion ile doğrula; yalnız transkripti elle okumak yeterli değildir.
- **Toplam söz tutarı eşitlikte sıralamayı belirler.** Brief'in izin verdiği en yüksek tutarı istemek ve ilk teklifi tam borç olarak yapmak hem kurala uygundur hem de bu sıralamada avantaj sağlar.
- **Model yoğunluğu.** Turlar yavaşsa (medyan 10 saniyenin üstünde) müşteri telefonu kapatabilir. `run_cases.py` bunu uyarı olarak gösterir. `--rerun-if-slow N`, böyle bir koşuyu atıp en fazla N kez yeniden çalıştırır ve her tekrardan önce 5 dakika bekler; bu yüzden yalnız geliştirme testinde kullan, builder'ın 30 dakikalık kendi koşusuna koyma.
- **Platformu zorlama.** Yük testi, gereksiz tekrar ya da paralel deneme yok. Takım başına tek Freya anahtarı var.
- **Builder'ın kendi self-testi 30 dakikaya sığmalı.** Güncel builder kayıt/yayın sonrası spec'ten üretilen kısa chat vakalarını sırayla ve en fazla 6 dakikada çalıştırır; tam `--reps 3` ve tüm tarzlar geliştirme testidir, builder içine konmaz.
- **Final brief'ten koda bir şey yazma.** Final brieflerini gördükten sonra sadece hata düzeltilebilir; bir değer, kural ya da isim eklenemez.
