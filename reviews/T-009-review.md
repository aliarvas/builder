# T-009 review (prompt bütçesi, kural yerleri, `enforced_by`)

Rapor: tasks/T-009-report.md; dosyalar `builder/spec.py`, `builder/workflow.py` (RulePlan, `build_spec_workflow`), `builder/prompts.py` (extraction bağlamı), `builder/build.py` (yalnızca render çağrısı ve trace satırları), `tests/test_prompt_budget.py`. Kod düzenlemedim, model veya Freya'ya istek atmadım. `python3 -m unittest`: paket geçiyor (194).

## Karar: merge edilebilir (iki not ile)
Mantık doğru ve açıkça sınırlı: kural yalnızca etiketliyse, etiketin kontrolü bu spec'te gerçekten çalışıyorsa ve yalnızca bütçe aşımında prompt'tan çıkıyor; her kuralın yeri trace'te; sert sınır aşılınca build açık hatayla duruyor. İki not: (1) etiketli kapanış kuralları bütçe baskısı olmadan da daima koda sayılıyor (bulgu 1), final koşudan önce düzeltilmeli; (2) "etiketsiz çok ürünlü brief'te build durur" davranışı CTO'nun kabul ettiği bir risk, aşağıda tarif edildi (bulgu 2).

## Bulgular

### 1. [Orta] Etiketli kapanış kuralları her zaman "koda" gidiyor, bütçeye bakmadan
- `RulePlan.__init__`: `closing.*` anahtarlı ve `_code_ok` olan her kural hemen `_to_code` ile hiçbir prompt'ta yer almıyor ("Closing rules guaranteed by the closing code never needed a prompt"). `enforcement_available("closing_outcome")` her spec'te `True` döndürüyor. Diğer kontrollerden farklı olarak bu kural *hiç* bütçe baskısı gerektirmiyor.
- Risk (F-042): kodun kapanışta yapmadığı bir mantık (örneğin Brief B'deki "her ürün `paid` notluysa `paid`", "ilk `paid` olmayan notun reason'ı") bir model tarafından yanlışlıkla `closing_outcome` etiketlenirse bu kural sessizce prompt'tan ve koddan kaybolur; trace yalnızca `code: closing_outcome` der. Prompt'taki etiket tanımı ("closing logic the table cannot express stays untagged") model dürüstlüğüne dayanıyor; kod doğrulamıyor. Rapor da F-042 iskelet açığını biliyor.
- **Düzeltme:** etiketli kapanış kuralları diğer etiketlerle aynı politikayı izlesin: varsayılan olarak global prompt'ta kalsın, yalnızca bütçe aşımında (`drop_code_enforced` aşaması) koda alınsın. Bu şekilde kodun garanti etmediği bir kuralı yanlış etiketlemenin bedeli bütçe aşımına kadar sıfır olur. Maliyet: tüm adımlara birkaç kural cümlesi (global prompt'tur). Bütçe testindeki etiketli A+B beklentisi buna göre güncellenir.

### 2. [Bilgi / karar] Sert sınır build'i durduruyor: etiketsiz çok ürünlü bir çıkarma tüm teslimi kaybettirir
- Doğrulama: canlı A+B spec'i (`brief-ab-extracted.json`) etiketsiz: `negotiate` 1680 → 1596 token, `SpecError` ("prompt budget exceeded ... no policy rule is cut"), build duruyor; aynı spec'in elle etiketli kopyası geçiyor (1595 → 1314, uyarı). Kural yerleri hata anında da trace'e yazılıyor (`placements` hata öncesi eklenmiş).
- Bu istenen davranış (kural kesme yok). Ama Freya'nın 500–1.500 token tavsiyesi bir öneri; platform sert sınır koymuyor. Final briflerden biri Brief B gibi çok ürünlü ve ham materyal olabilir; yeni extraction prompt'u etiketleri istiyor, ama model etiketlemezse build durur ve o brief'ten sıfır puan gelir. "Durup hata vermek" ile "uyarıyla 1.500–~2.000 token'lık bir prompt göndermek" arasında seçim CTO'nun. Önerim: sert sınır `SpecError` olarak kalsın ama ikinci bir üst sınır (ör. 2.200) arasında yalnızca uyarı + trace (`budget_exceeded_but_shipped`), tamamen durma yalnızca bu üst sınırın üstünde olsun. Karar CTO'nun; mevcut davranış de savunulabilir.

### 3. [Düşük] `enforcement_available` bazı kontroller için her zaman `True`
- `offer_dates`, `invalid_offer_limit`, `identity_attempts`, `closing_outcome` veri koşulu aranmadan `True`. Ör. `offer_dates` etiketli bir kural ("en geç tarih ... brief'in belirttiği") spec'te `latest` kuralı olmasa bile koda sayılır. Kodda `earliest` zorunlu olduğu için "en erken" doğru; "en geç" kuralı yoksa kod bir en geç tarih üretmez (`latest` boş = en geç tarih yok). Yani yalnızca "latest" ile ilgili etiketli bir kural veri olmadan çıkabilir. Düzeltme: `offer_dates` için `latest` listesi boşsa ve kural son tarihten söz ediyorsa kalsın; basit hâliyle etiket yalnızca `earliest` veya `latest` verisi varken geçerli say.

### 4. [Bilgi] Etiket tanımında "exactly once"
- Prompt: "the closing tool is called exactly once and last". Workflow başarısızlıkta bir yeniden deneme yapıyor (iki çağrı, ikisi de başarısızsa). "Tek başarılı çağrı" demek daha doğru; kod ve test (T-007b bulgu 1) tutarlı olsun.

## Doğrulananlar

| Kontrol | Sonuç |
|---|---|
| `enforced_by` etiketi | `Rule.enforced_by` isteğe bağlı; yedi değer (`offer_dates, business_days, offer_amounts, weekday_reading, invalid_offer_limit, identity_attempts, closing_outcome`), bilinmeyen değer `SpecError`; eski spec'ler değişmeden geçerli. |
| `enforcement_available` mantığı | Etiket tek başına yetmiyor: `business_days` → `promise_date_must_be_business_day`; `offer_amounts` → min/max kuralı var; `weekday_reading` → `next_weekday != ask`. Veri yoksa kural prompt'ta kalıyor ve trace "this spec has no data for that check, kept" yazıyor (testli, `next_weekday=ask` örneği). Bulgu 3 dışında doğru. |
| Bütçe aşamaları | Yalnızca hedefi (1200) aşan bir adım varsa, sırayla: (1) etiketli ve kontrolü mevcut kurallar çıkar, (2) tam cümle kopyaları (büyük/küçük harf, noktalama, tanımlıklar yok sayılarak; cümle parçası eşleşmesi yok, "offer the floor" / "do not offer the floor" korunuyor), (3) birden çok adımda geçen kural global prompt'a taşınır. Her aşamadan sonra yeniden render ve ölçüm. Sert sınır (1500) hâlâ aşılırsa `SpecError`. |
| Hiçbir kuralın sessizce kaybolmaması | Canlı spec'lerde (f040-a: 71 kural, A+B: 84, f041-a: 69) `placements` sayısı kural sayısına eşit; her kuralın yeri ve nedeni (`its section`, `code: <etiket>`, `duplicate of <anahtar>`, `moved: ...`, `closing rule, not guaranteed by code`) yazılıyor. Etiketli kopyada 13 kural koda, 4 kural kopya olarak ayrıldı, geri kalanı yerinde. Eskiden hiçbir prompt'a girmeyen `closing.rules` artık global prompt'ta (etiketsizler) ya da koda gidiyor (F-042'nin sessiz kaybı kapanmış; bulgu 1 ile sıkılaştırılmalı). |
| Trace'te kural yerleri | `rule_placement:` her kural için bir satır, `budget:` değişen/aşan adımlar için `~önce -> ~sonra (hedef, sınır)` ve aşama listesi; hata yolunda da (finally) yazılıyor. |
| Extraction prompt'u brief değeri içeriyor mu | **Hayır.** Eklenen "RULES THE PROGRAM ALREADY ENFORCES" bölümü yedi değeri genel dille tanımlıyor ve etiketlenmeyecekleri açıkça sayıyor ("anything the agent must say, ask, propose or decide ... a rule that covers two checks is split"). Üç brief ve raw-a dosyalarından çıkardığım jetonlarla taradım: ortak snake_case kod yok; ortak rakamlar yalnızca genel (`25 words` kaynak sınırı, `1 = Monday ... 7 = Sunday`). Sızıntı testi yeşil. |
| Sert sınır aşılınca build durur | **Evet.** Etiketsiz A+B canlı spec'i açık `SpecError` ile duruyor (adım adı ve token sayısı mesajda); küçük spec'lerde ve changed-a/Brief A'da çalışma değişmiyor; 60 sentetik kuralla koruma ve hata testli. |

## Kurallara uyum
Freya/model isteği yok, `run_trace.py` ve `tools/submission_check.py`'ye dokunulmamış, `build.py`'de yalnızca render çağrısı ve trace satırları değişmiş.

## Düzeltme sonrası
Bulgu 1 düzelince: etiketli A+B kopyasında `negotiate` ve global prompt boyutlarını yeniden ölç (kapanış kuralları artık global prompt'ta kalacağı için artış beklenir, tüm adımlar 1500 altında kalmalı). Canlı tekrarda `rule_placement` satırlarında kaç kuralın `code:` olduğuna ve etiketlerin yalnızca tarih, tutar, iş günü, gün okuma, kimlik sayımı ve kapanış tablosu kurallarında olduğuna bakın.
