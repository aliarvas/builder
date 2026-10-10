# T-005b raporu: global özel yollar, deterministik çıkışlar, kodla teklif kontrolü

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

Görevdeki üç parça da yapıldı. `python3 -m unittest` 75 testin hepsini geçiyor (öncesi 62). `--print --spec` fixture A ve B ile çalışıyor. Hiçbiri Freya'da denenmedi; aşağıdaki TO-CONFIRM noktaları chat testinde doğrulanmalı. Freya'ya istek yok, commit yok, `env.sh` okunmadı, `builder/` içinde brief değeri yok.

Değişen dosyalar:

- **Kod:** `builder/spec.py`, `builder/workflow.py`, `builder/prompts.py`, `builder/build.py` (trace'e global node sayısı) ve yeni `builder/offer_check.py`.
- **Test ve fixture:** `tests/test_multi_step.py`, `tests/fixtures/spec-*.json` (üçü de).
- **Doküman:** `docs/PROMPTS.md` (yeniden üretildi), `docs/UAT-FINDINGS.md` (F-003, F-011).

## Adım sayısı: önce / sonra

Sayılar fixture ile kit OpenAPI'sinden alındı; "önce" değeri HEAD `6cd46fb`'dir.

| Fixture | Normal adım | Global adım | Sohbet adımı | Özel yol adımı |
|---|---|---|---|---|
| A önce | 36 | 0 | 12 | 7 (`special_<id>_from_<adım>` kopyaları) |
| A sonra | 34 | 3 | 8 | 4 (3 global + 1 `special_human_go`) |
| B önce | 32 | 0 | 10 | 5 |
| B sonra | 32 | 2 | 7 | 3 |

Toplam adım sayısı az değişti, çünkü yeni kod adımları eklendi: `offer_setup`, `check_offer`, `close_offer_limit`, `close_special_tool_failed`. Model kullanan sohbet adımı ise A'da 12'den 8'e, B'de 10'dan 7'ye indi. Trace artık `global_nodes: N` satırını da yazıyor.

Prompt bütçesi (A): en büyüğü identity, yaklaşık 506 token; negotiate yaklaşık 240, confirm_record yaklaşık 231. Hepsi 1.500 altında.

## 1. Özel yollar global node

- **Global node yapısı:**
  - Her `special_paths` öğesi için tek bir global node var: `special_<id>`. Koşulu, spec'teki `when` metniyle `matches_intent`.
  - Adım kopyaları (`special_<id>_from_*`) kalktı.
  - Normal adımlarda artık hiç `matches_intent` geçişi yok.
- **`excluded_nodes`:** yolun `available_in` listesindekiler dışındaki her normal adım, artı bütün global node'lar (kendisi dahil). Böylece opening ve identity yalnızca spec listelerse dahil oluyor. Kapanış zinciri, `end_call` ve kod adımları da hep hariç.
- **Çıkış hedefleri:**
  - `then: return` → `__previous__`.
  - `then: close` → `close_special_<id>`.
  - Close yolunda araç başarısız olursa → `close_special_tool_failed`. Bu yeni isteğe bağlı bitiş durumu; spec eşlemezse `default` satırına düşüyor.

## 2. Deterministik özel çıkışlar

Spec'te iki değişiklik var:

- `say` artık **birebir söylenen cümle**. Üç fixture'da da talimat metinleri cümleye çevrildi.
- İsteğe bağlı `ask` (önce sorulan soru) eklendi. Yalnızca `then: close` ile kullanılabiliyor; aksi halde SpecError.

Yolun biçimini araç belirliyor:

| Durum | Adım | Çıkış |
|---|---|---|
| Araç yok | Passthrough adım, `on_enter` tts ile `say` | Her zaman → hedef |
| Araç var, bütün zorunlu alanlar sabit | `api_request`: `on_enter` tts `say`, engine aracı çalıştırır (`maxRetries: 0`) | `data.ok` true → başarı; aksi halde → başarısızlık |
| Araç modelin doldurması gereken bir alan istiyor (B `add_note`: ürün) | Sohbet adımı, araç `tools` içinde | Aracın `response_mapping` sonucu (`special_result_<id>` true/false) |
| `ask` var | Global adım soruyu tts ile sorar ve `proceed/stay` çıkarır | `proceed` → `special_<id>_go` (yukarıdaki biçimlerden biri); `stay` → `__previous__` |

- Hiçbir özel yol çıkışı `matches_intent` veya `is_tool_call` kullanmıyor (testli).
- Ürün kimliği alanı modele bırakılmıyor. `_with_product_number` her araçta `product_id`'yi ürün numarasıyla değiştiriyor ve id'yi bir hook yerleştiriyor (rereview N5 kapandı, B `add_note`).
- `special_result_<id>` değişkenleri `check_offer` her çalıştığında temizleniyor. Böylece bir yol ikinci kez tetiklendiğinde eski sonuç kullanılmıyor.

## 3. Teklif kontrolü kodla (`check_offer`)

### Akış

`account` → `offer_setup` (kod) → `negotiate` → `check_offer` (kod) → `confirm_record` / `negotiate` / `close_offer_limit`

- **`offer_setup`:** her ürün için bir olgu satırı üretir: alanlar, en erken ve en geç tarih (gün adıyla), asgari ve azami tutar. Bugünü yazar. Prompt'ların okuduğu her değişkene başlangıç değeri koyar.
- **`negotiate` çıkarımı:** veri olarak `offer_date` (tip `date`), `offer_amount` (`float`), `offer_product_number` (`integer`), artı mevcut niyet ve ürün sayısı.
- **`negotiate` çıkışları:**
  - `offer_date` ve `offer_amount` dolu ve boş değilse → `check_offer`. `proposal` etiketi artık gerekmiyor.
  - Niyet bitti/ret ise ve kabul edilmiş teklif varsa → `confirm_record`.
  - Ret ise ve hiç kabul yoksa → kapanış.
- **`check_offer`:**
  - Sonucu ve önerilen tarih/tutarı yazar, `prompts.py`'deki `OFFER_VERDICT_MESSAGES`'tan ajan için bir cümle seçer.
  - Kabul edilen teklifleri `offers_accepted`'a (ürün numarası → id, tarih, tutar) ve okunabilir `offers_summary`'ye yazar.
  - `offer_date` ve `offer_amount`'ı boşaltır ve niyet değişkenlerini sıfırlar (N6).
- **Reddedilen teklif sayacı:** yalnızca **farklı** teklifleri sayar; extractor aynı eski teklifi tekrar getirirse sayaç artmaz. Sınır spec'ten (`max_rejected_offers`) gelir; sınırda → `offer_limit` kapanışı.
- **Çok ürün:** kabul sayısı, müşterinin söz verdiği ürün sayısına ulaşınca `ready` → `confirm_record`; ulaşmadıysa `more` → sıradaki ürün.
- **`create_promise`:** model yalnızca ürün numarasını veriyor. Tarih, tutar ve ürün kimliğini bir ön-hook kontrol edilmiş tekliflerden (`offers_accepted`) koyuyor; şemadaki tarih ve tutar alanları kaldırıldı. Alan adları spec'ten geliyor (`confirmation.promise_date_field`, `promise_amount_field`). `confirmation_progress` kaydedilecek ürün sayısını kabul edilen tekliflerden alıyor.
- **Kod güvenliği:** kod `vars` dışında bir şey okumuyor, hata atmıyor (testli). İçinde `{{`/`}}` yok; spec verisi kaçırılmış JSON olarak gömülüyor.

### Kural formatı (`spec.offer`)

```json
"offer": {
  "rules": [],
  "today_variable": "now",
  "non_business_weekdays": [6, 7],
  "holidays": ["YYYY-MM-DD", "..."],
  "promise_date_must_be_business_day": true,
  "earliest": {"days": 0, "unit": "calendar"},
  "latest": [
    {"when": [{"field": "<ürün alanı>", "min": 1, "max": 7}], "days": 12, "unit": "business"},
    {"when": [{"field": "<ürün alanı>", "min": 8, "max": 45}], "days": 7, "unit": "business"}
  ],
  "latest_on_non_business_day": "previous",
  "min_amount": [
    {"when": [{"field": "<ürün alanı>", "in": ["<değer>"]}], "field": "<ürün alanı>"},
    {"value": 10},
    {"field": "<ürün alanı>", "share": 0.5}
  ],
  "max_amount": [{"field": "<ürün alanı>"}],
  "max_rejected_offers": 3
}
```

- **Alanlar:**
  - `unit`: `business` veya `calendar`. Takvim günlü son tarih iş gününe denk gelmezse `latest_on_non_business_day` uygulanır: `previous`, `next` veya `keep`.
  - `when`: ürün alanları üzerinde koşul listesi (`min`, `max`, `equals`, `in`); hepsi tutmalı. `when` yoksa kural hep geçerli. Kurallardan ilk eşleşen kazanır. `latest` için hiçbir kural eşleşmezse son tarih yok.
  - `non_business_weekdays`: ISO hafta günü numaraları (1 = Pazartesi … 7 = Pazar).
- **Bugün:** `now` çağrı değişkeninden alınıyor; yoksa sistem tarihi.
- **Kontrol sırası:**
  1. ürün belirsiz → `product_unknown`
  2. tarih veya tutar eksik → `missing`
  3. en erken tarihten önce → `date_too_early`
  4. en geç tarihten sonra → `date_too_late` (son tarihi önerir)
  5. iş günü değil → `date_not_business_day` (sonraki iş gününü önerir, son tarihi aşarsa son tarihi)
  6. asgari tutarın altında → `amount_too_low`
  7. azami tutarın üstünde → `amount_too_high`
  8. hiçbiri değilse `ok`
- **Fixture'lar:** A ve B aynı kuralları kullanıyor. Synthetic bilerek farklı: yalnızca Pazar tatil, en erken tarih 1 iş günü sonra, en geç tarih 20 takvim günü (`next` ile kayar), iş günü şartı yok, asgari tutar borcun yarısı, ret sınırı 2.

### Testler (elle hesaplanmış beklenenler)

- **A, bugün 2026-10-14 Çarşamba:**
  - erken bant son tarihi 2026-11-02 (12. iş günü, 26 Ekim tatili atlanır); 11-03 → son tarih önerilir;
  - tatil 10-26 → 10-27; Cumartesi 10-17 → 10-19; dün → bugün;
  - asgari tutar 28.50, borç üstü → 95.00; kredi tipinde asgari tutar 150;
  - geç bant son tarihi 10-23; 10-26 → 10-23;
  - "next week" ve boş tutar → `missing`.
- **B:** iki üründe numara yoksa `product_unknown`; ürün 1 kabul → `more`, ürün 2 kabul → `ready`, özet ve `offers_accepted` doğru.
- **Synthetic:** en erken tarih, takvim günü son tarihinin Pazar'dan Pazartesi'ye kayması, Pazar'ın kabul edilmesi, yarı tutar.
- **Ret sayacı:** aynı teklif iki kez → 1; sonraki farklı teklifler → 2 ve 3 → `limit`.
- **Bozuk girdiler:** boş, bozuk JSON, `None` → hata yok, bütün çıktı değişkenleri dolu.
- **Spec doğrulaması:** ISO olmayan tatil, geçersiz hafta günü, bilinmeyen `unit`, hem `field` hem `value`, sıfır sınır, koşulsuz `when` → açık hata.

### Sızıntı testi

- İzin listesine spec.py'deki `OFFER_UNITS`/`OFFER_ADJUST` sözlüğü eklendi (`business`, `calendar`, `previous`, `next`, `keep`).
- OpenAPI'nin **alan adları** da değerleriyle birlikte sözleşme sayılıyor. Ürün alanı adları (`type`, `days_late` vb.) bankanın API'sinden geliyor, brief'ten değil.
- Yeni spec alanları taramaya otomatik giriyor.

## Tasarım seçimleri ve neden

- **Özel yol ve teklif kodu ayrı.** Teklif kodu `builder/offer_check.py`'de duruyor; `workflow.py` zaten büyüktü.
- **Tek ürün tasarımı yerine "kabul edilen teklifler" listesi.** Brief B'de bütün sözler birlikte geri okunuyor ve her ürün için ayrı `create_promise` çağrılıyor. Değerleri adım girişinde sabitlemek tek ürüne yeterdi, çok ürünü taşımazdı. Bu yüzden model yalnızca ürün numarasını veriyor, hook değerleri kontrol edilmiş listeden koyuyor.
- **`ask` yalnızca `then: close` ile.** `ask` sonrası adım normal bir adım. Normal adımdan `__previous__`'a dönüşü kit yalnızca global node'lar için tanımlıyor.
- **Modelin doldurduğu araçlı global yolda eski sonuç riski.** Bunu `check_offer`'da sıfırlayarak azalttım. Bu tür yolun dönüşü zaten `negotiate` → `check_offer` üzerinden geçiyor.
- **Teklif değişkenlerini sıfırlarken boş metin.** `is_set` boş metni dolu sayabilir. Bu yüzden negotiate çıkışı `is_set` + `not_equals ""` birlikte kullanıyor.

## TO-CONFIRM (chat testi)

**Genel:**

1. Global node, adımın yalnızca deterministik geçişleri varken bir kullanıcı mesajıyla tetikleniyor mu? Kit "adımın kendi geçişleri eşleşmezse global node'lar kontrol edilir" diyor; self-loop'lar T-005a'da kalktı.
2. Bir passthrough global node (tts + `__previous__`) ve `api_request` tipinde bir global node (tts + `pre_actions`) çalışıyor mu? Kit örneği yalnızca tts + passthrough sohbet tipi bir global node gösteriyor.
3. `__previous__` doğru adıma dönüyor mu (B `product_dispute`: negotiate veya confirm_record)?
4. Ön-hook'un `config['body']`'ye eklediği alanlar (`product_id`, tarih, tutar) istekte gerçekten gidiyor mu? Bu, T-004'teki ürün kimliği hook'uyla aynı varsayım.

**PUB-01 (söz):**

- `offer_date` (tip `date`) hangi biçimde geliyor? Kod metin içinde `YYYY-MM-DD` arıyor.
- "Can you pay today?" sorusuna "yes" denince extractor bugünün tarihini ve tutarı çıkarıyor mu? Çıkarmazsa ajanın tutarı söyleyip tekrar sorması gerekir.
- `check_offer` → `confirm_record` aynı turda mı oluyor?
- `create_promise` doğru id, tarih ve tutarla gidiyor mu? Ledger'dan bakılmalı.
- Ret sayacı extractor'ın eski teklifi tekrar getirmesiyle şişiyor mu?

**PUB-07 (geri arama):**

- third_party adımı bu turda değişmedi; global node'lar orada tetiklenmiyor (`available_in` dışında).
- Gözlenecekler: `schedule_callback` sonucu aynı turda `close_callback_scheduled`'a gidiyor mu, ve geri arama saat penceresi hâlâ model tarafından mı doğru uygulanıyor? Pencere kontrolü henüz kodda değil.

## Açık sorular (T-006 extractor ne üretmeli)

1. **`offer` bölümü:**
   - takvim (iş günü olmayan günler, tatiller), bugün değişkeni;
   - en erken/en geç tarih kuralları: bant tablosu `when` koşullarına; "iş günü" ve "takvim günü" ayrımı;
   - asgari/azami tutar kuralları: ürün tipine göre alan, sabit değer veya oran;
   - `max_rejected_offers`. Brief A'da açık bir sayı yok; ikna denemesi kuralı (rule 30) ayrı bir şey.
2. **Özel yollar:** `say` birebir cümle olmalı. "Önce sor" gereken yollar için `ask` dolmalı (A kural 42).
3. **`confirmation.promise_date_field` / `promise_amount_field`:** OpenAPI'den.
4. **Kapsam dışı kalanlar:**
   - A kural 30'daki "bu haftanın son iş günü" ve "son tarihte asgari tutar" gibi ikna önerileri hâlâ prompt'ta; kodda hesaplanmıyor.
   - B kural 6 (tek tarih bir ürünün son tarihini aşarsa o ürün kendi son tarihine) kısmen var: `check_offer` son tarihi öneriyor, otomatik uygulamıyor.
   - Geri arama penceresi (A kural 6–7) kodda değil.
5. **`confirm_record`'da değişiklik:** müşteri geri okumada tarihi değiştirirse akış `negotiate`'e dönüyor ve yeni değer orada tekrar istenmeli. `confirm_record`'a teklif çıkarımı eklemedim; ajanın kendi geri okumasını yeniden çıkarıp döngüye girme riski var.
