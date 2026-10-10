# Self-test: organizatör gibi test etmek

Bu doküman, builder'ı organizatörün final testine benzer şekilde nasıl test edeceğimizi anlatır: hangi araçları kullanacağımızı, hangi sırayla ilerleyeceğimizi, neye dikkat edeceğimizi. Test verisi kitte hazır (`build-the-builder-v2/public-test-set.json`); burada yeni veri tanımlanmaz.

Kaynaklar: hackathon sayfası (https://www.freyavoice.ai/hackathon#evaluation), `build-the-builder-v2/README.md`, `build-the-builder-v2/docs/`. Genel test kuralları [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md) dosyasındadır; bu dosya onu adım adım uygular.

## Organizatör ne yapıyor (bizim taklit ettiğimiz şey)

- **Final briefleri:** İki gizli brief, her biri 30 müşteri; toplam 60. Briefin biri temiz bir spesifikasyon, diğeri ham banka malzemesi.
- **Müşteriler:** 1 ile 3 arası ürün. Birkaç farklı takvim gününe dağılmış. İnsan gibi konuşuyorlar.
- **Tekrar:** Her müşteri 3 kez koşulur. Üçü de geçerse müşteri geçmiş sayılır.
- **Üç kontrol:** Outcome (banka kayıtları), Policy (judge modeli), Honesty (judge modeli). Kısmi puan yok. Doğru bir ret de geçer; örneğin müşteri borca itiraz eder ve hiç söz kaydedilmezse.
- **Skor:** Geçen müşteri / 60. Eşitlikte sırasıyla: geçen müşterilerdeki toplam söz tutarı, trace'teki toplam build süresi, teslim zamanı.
- **Doğrulama:** İlk 10 takımın commit'i klonlanır ve builder yeniden çalıştırılır. Sonuç trace ile karşılaştırılır. Bir reviewer agent trace, kod ve ajanları karşılaştırır. Yeniden çalıştırmada skoru belirgin düşen takım elenir.

## Araçlar

| Araç | Ne için |
|---|---|
| `python3 builder/build.py {brief} {tool_api}` | Resmi komut. Testi hep bu komutla yap, ek bayrak kullanma |
| `python3 builder/build.py --print ...` | Freya'ya gitmeden workflow JSON'unu üret. Yapı kontrolü için |
| `python3 builder/build.py --validate ...` | Freya dry run. Kaydetmeden şemayı doğrular |
| `python3 -m unittest` | Offline birim testleri |
| `POST /api/v2/chat/message` | Tek tek chat turu. Hızlı ilk kontrol (api.md) |
| `build-the-builder-v2/tools/run_cases.py <agent_id>` | Pratik müşterileriyle simülasyon. Banka kaydı ve judge ile puanlar |
| `run_cases.py` seçenekleri | `--brief A\|B`, `--only PUB-03,...`, `--reps 3`, `--style pieces\|corrects\|talkative\|asks_back\|in_words`, `--out results/run.json`, `--rerun-if-slow N` |
| `freya.get_call(call_id)["messages"]` | Başarısız bir görüşmenin tam kaydı. `route_evaluated` olayı bir geçişin neden çalışıp çalışmadığını gösterir |
| `freya.export_workflow(workflow_id, path)` | Teslim edilecek dosya. Puanlanan şey bu dosya |

**Ortam değişkenleri:** `FREYA_API_KEY` ve `FREYA_BANK_TEAM_KEY` gerekir. `FREYA_BANK_TEAM_KEY` kendi seçtiğimiz, her seferinde aynı olan bir anahtardır.

**Onay kuralı:** `--print` ve `unittest` dışındaki her adım Freya'ya istek atar: kayıt, dry run, chat ve simülasyon. Bunların her biri için önce kullanıcı onayı alınır (`AGENTS.md`, madde 6).

## Adımlar

### Adım 1. Offline kontroller (onay gerekmez)

1. `python3 -m unittest` çalıştır; hepsi geçmeli.
2. `--print` ile Brief A, A+B ve sentetik spec için workflow üret.
3. Üretilen JSON'u kit dokümanlarındaki kurallara karşı kontrol et. Kontrol listesi: [`reviews/KIT-V3-COMPLIANCE.md`](../reviews/KIT-V3-COMPLIANCE.md). Başlıca kurallar:
   - `null` yok, `agent_config` yok.
   - Passthrough düğümleri `always` geçişiyle biter.
   - `tools` sadece konuşma düğümlerinde, `pre_actions` sadece code ve api düğümlerinde.
   - Mapping yolları `data.` ile başlar.
   - Boolean karşılaştırmalar `"true"` ve `"True"` ile, iki yazımla da yapılır.
   - Code içinde `{{` ya da `}}` yok.
   - Tool'suz adımlarda "bu turda tool çağırma" cümlesi var.
4. **Hardcode taraması:** `builder/` klasöründe pratik brieflerin değerlerini ara. Bulunmaması gerekenler:
   - tatil tarihleri, tutarlar, limitler,
   - sonuç ve not kodları,
   - kimlik soruları,
   - "Freya Bank" adı.

   Bulunan her değer, gizli brief'te yanlış çalışacak bir koddur.

### Adım 2. Görülmemiş brief provası (en önemli adım)

Organizatör bizim görmediğimiz bir brief verecek. Bunu taklit et:

1. **Ham malzeme versiyonu:** Brief A'yı ham malzeme haline getir: mail, politika parçası, kuralı değiştiren bir not, kod listesi. Builder aynı ajanı üretmeli.
2. **Kural değişikliği versiyonu:** Brief A'nın sayılarını, kimlik sorularını, sonuç tablosunu ve takvimini değiştir.
3. **Farklı OpenAPI:** Tool adları aynı kalsın, alanları ve izin verilen değerleri (enum) değiştir. Builder alanları dosyadan okumalı.

Bu dosyalar test verisidir; `tests/` altında durur, `builder/` altına girmez. Builder hata vermeden, elle adım olmadan, 30 dakika içinde bitmeli.

**Şart:** Bu adım T-006 sonrası anlamlıdır. T-006'da builder spec'i brief'ten kendisi çıkaracak. O zamana kadar `--spec` ile elle yazılmış spec kullanmak final testini taklit etmez.

### Adım 3. Resmi komutla build (onay gerekir)

1. `python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json`
2. Brief B için iki brief'i birden ver: `brief-a.md brief-b.md openapi.json`.
3. Kontrol et:
   - **Süre:** 30 dakikanın altında mı? Bu süreye builder'ın kendi self-testleri de dahil.
   - **Workflow:** Aynı slot yerinde mi güncellendi? Yeni workflow açılmamalı (workspace sınırı 200).
   - **Yayın:** Son versiyon yayınlandı mı (`isPublished`)? Yayınlanmamış bir versiyon simülasyonda kullanılmaz.
   - **Export:** `submission/<slot>.workflow.json` dosyası oluştu mu?

### Adım 4. Trace kontrolü (reviewer agent gibi oku)

Trace'te şunlar olmalı:

- başlangıç ve bitiş saati,
- her model çağrısı: model adı ve bir satırlık amaç,
- Freya'da kurulan `workflow_id` ve `agent_id`,
- builder'ın yaptığı her self-test ve sonucu.

Ayrıca:

- **API anahtarı olmamalı.** `fak_` ile başlayan değer ya da team key trace'e girmemeli.
- **Trace kod ve ajanla uyumlu olmalı.** Reviewer agent ikisini karşılaştıracak. Trace "self-test yapıldı" diyorsa, kodda da gerçekten o test olmalı.

### Adım 5. Chat testi (onay gerekir)

1. Seçilen bir pratik müşterisi için `customerVariables` ile tek tek tur gönder. `now` değerini case dosyasından al.
2. Ajan konuşmayı başlatıyor mu, tool çağırıyor mu, tool'dan sonra konuşuyor mu, bak.
3. Bulunan her hatayı [`UAT-FINDINGS.md`](UAT-FINDINGS.md) dosyasına yaz: belirti, kök neden, çözüm, durum.

Chat geçmeden simülasyona geçme.

### Adım 6. Simülasyon: önce tek tur, sonra final koşulları (onay gerekir)

1. **Tek tur:** `run_cases.py <agent_id> --brief A` ve `--brief B`. Bu sadece ilk sinyal; tek yeşil sonuç kanıt değildir.
2. **3 tekrar:** `--reps 3`. Bir müşteri, üç çalıştırmanın üçü de geçerse sayılır. Final de böyle sayıyor.
3. **Konuşma tarzları:** Her tarzla ayrı koş: `pieces`, `corrects`, `talkative`, `asks_back`, `in_words`. Final müşterileri bunların karışımı gibi konuşur.
4. **Hata enjeksiyonu:** PUB-10'da `create_promise` ilk denemede başarısız olur. Ajan dürüst kalmalı ve tekrar denemeyi doğru yapmalı.
5. Her koşuda `--out results/<tarih>-<koşu>.json` ile call id'leri sakla.

**Süre:** Bir simülasyon bir seferde çalışır; ikinci `run_cases.py` birincisini bekler. 10 müşteri 3 ile 11 dakika sürer, `--reps 3` ve beş tarz ile toplam saatler sürebilir. Sırayı ve süreyi önceden planla.

### Adım 7. Başarısız müşteriyi analiz et

1. `run_cases.py` çıktısında kontrolün hangisinin kaldığına bak: banka kaydı mı, judge mı?
2. `freya.get_call(call_id)["messages"]` ile görüşmeyi oku. `route_evaluated`, `function_call_start` ve `function_call_complete` olaylarına, `variable_table`'a bak.
3. Kök nedeni builder'da düzelt; ajanı asla elle düzeltme. Sonra yeniden build et.
4. Bulguyu `UAT-FINDINGS.md` dosyasına yaz.

### Adım 8. Yeniden üretilebilirlik (top 10 doğrulaması)

1. Temiz bir checkout'tan builder'ı aynı brief ile ikinci kez çalıştır.
2. İki çalıştırmanın skorlarını ve trace'lerini karşılaştır. Skor belirgin düşüyorsa organizatör de aynısını görür ve takımı eler.
3. Çalıştırmalar arası fark büyükse sebebini bul: LLM çıktısının değişkenliği, ya da zamana bağlı bir değer.

### Adım 9. Teslim provası

1. Her brief için ajan dosyası (`export_workflow`), commit ve trace hazır olmalı.
2. Trace'te anahtar olmamalı.
3. Ajan dosyası builder'ın o çalıştırmasından gelmeli; elle düzeltilmiş olmamalı.

## Dikkat edilecekler

- **Puan yüzdesi değil, 3/3 önemli.** Çoğu zaman doğru olan bir ajan, finalde doğru sayılmaz.
- **Önce kontrol, sonra konuşma kalitesi.** Banka kaydı ve judge kontrolleri, akıcı konuşmadan önce gelir.
- **Dürüstlük.** Tool başarısızsa ajan asla "kaydettim" dememeli. PUB-10 bu senaryoyu test eder.
- **Takvim günleri.** Tüm pratik müşterilerinde `now` aynı: `2026-10-14T11:00`. Final ise birkaç farklı günde koşuyor.
  - Ajanın "bugün" bilgisini `now` call değişkeninden aldığından emin ol, `system.*` tarihlerinden değil.
  - Farklı bir `now` ile test için case dosyasını kopyala ve `--cases` ile ver.
  - Dikkat: `now` değişince beklenen söz tarihleri de değişir. Bu yüzden böyle bir koşuda banka kaydı puanına güvenme; transkripti ve tarih hesabını elle kontrol et.
- **Toplam söz tutarı eşitlikte sıralamayı belirler.** Brief'in izin verdiği en yüksek tutarı istemek ve ilk teklifi tam borç olarak yapmak hem kurala uygundur hem de bu sıralamada avantaj sağlar.
- **Model yoğunluğu.** Turlar yavaşsa (medyan 10 saniyenin üstünde) müşteri telefonu kapatabilir. `run_cases.py` bunu uyarı olarak gösterir. Böyle bir koşudaki düşük skor bizim hatamız olmayabilir; `--rerun-if-slow` ile tekrarla.
- **Platformu zorlama.** Yük testi, gereksiz tekrar ya da paralel deneme yok. Takım başına tek Freya anahtarı var.
- **Builder'ın kendi self-testi 30 dakikaya sığmalı.** Tam `--reps 3` ve tüm tarzlar bu süreye sığmaz. Builder içinde kısa bir kontrol yap (dry run ve birkaç chat turu); tam testi geliştirme sırasında yap.
- **Final brief'ten koda bir şey yazma.** Final brieflerini gördükten sonra sadece hata düzeltilebilir; bir değer, kural ya da isim eklenemez.
