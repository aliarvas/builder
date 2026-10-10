# T-009 raporu: prompt bütçesi ve kuralların yeri

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

- **Testler:** `python3 -m unittest` 186 testin hepsini geçiyor; 10'u yeni (`tests/test_prompt_budget.py`). Sızıntı ve prompt testleri yeşil; `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok, canlı çağrı yok.
- **Dokunulmayanlar:** `run_trace.py` ve `tools/submission_check.py`. `build.py`'de yalnızca render çağrısı ve trace satırları değişti; Codex'in commit edilmemiş değişikliklerine dokunulmadı.

**Sonuç:** Kodun zaten uyguladığı kurallar artık bütçe gerektiğinde prompt'tan çıkıyor. Bütçe koruması çalışıyor ve her kuralın yeri trace'te. Ancak **dürüst etiketlerle Brief A+B'de `negotiate` ~1314 token**: sert sınırın (1500) altında, hedefin (1200) üstünde. Hedefe inmek için ya etiketsiz bir kuralı atmak ya da kodun yapmadığı bir işi kod yapıyor saymak gerekirdi. İkisini de yapmadım; karar aşağıda.

## Tasarım

### 1. Etiket: `enforced_by`

- **Spec (`spec.py`):** `Rule` dataclass'ına isteğe bağlı `enforced_by` alanı eklendi (varsayılan boş, eski spec'ler aynen geçerli).
- **Değerler:** `ENFORCEMENT_CHECKS` içinde ve kodun gerçekten yaptığı işlerle sınırlı:
  - `offer_dates`, `business_days`, `offer_amounts`, `weekday_reading`: `offer_check`;
  - `invalid_offer_limit`;
  - `identity_attempts`: araç sayıyor;
  - `closing_outcome`: kapanış tablosu ve zinciri.
- Bilinmeyen değer `SpecError` veriyor.
- **Etiketin kapsamı (renderer):** Etiket tek başına yetmiyor. `enforcement_available(spec, check)` o kontrolün bu spec'te gerçekten çalışıp çalışmadığına bakıyor:
  - `business_days`: `promise_date_must_be_business_day` açık olmalı;
  - `offer_amounts`: tutar kuralı olmalı;
  - `weekday_reading`: `next_weekday` `ask` olmamalı.

  Etiket var ama veri yoksa kural prompt'ta kalıyor ve trace bunu yazıyor.
- **Extraction (`prompts.py`):**
  - Ortak bağlama "RULES THE PROGRAM ALREADY ENFORCES" bölümü eklendi. Yedi değeri tek tek tanımlıyor ve şunu söylüyor: ajanın söylemesi, sorması, önermesi ya da karar vermesi gereken her şey ve tablonun ifade edemediği kapanış mantığı etiketsiz kalır; iki kontrolü kapsayan kural ikiye bölünür.
  - `closing.rules` için not: çağrı sırasında yapılan işler (not, transfer) kapanışa değil, gerçekleştiği adıma yazılır.

### 2. Bütçe koruması (`workflow.py`, `build_spec_workflow`)

- **Ayarlar:** Hedef 1200, sert sınır 1500 token (`PROMPT_TARGET_TOKENS`, `PROMPT_HARD_LIMIT_TOKENS`; çağrıda değiştirilebilir). Tahmin mevcut `workflow_prompt_estimates` ile yapılıyor: sistem prompt'u + görev metni + araç açıklamaları, karakter/4.
- **Kural planı:** Render artık bir `RulePlan` üzerinden çalışıyor. Her kuralın yeri bir adım prompt'u, global prompt ya da "prompt'ta yok".
- **Aşamalar** (yalnızca hedefi aşan bir adım varsa ve sırayla):
  1. Etiketli ve kontrolü mevcut kurallar o adımdan ve global prompt'tan çıkıyor.
  2. Kopyalar kaldırılıyor. Yalnızca **tam cümle** düzeyinde: bir kuralın bütün cümleleri aynı adımdaki başka bir kuralda ya da global bir kuralda aynen geçiyorsa (büyük/küçük harf, noktalama ve tanımlıklar yok sayılarak). Cümle parçası eşleşmesi kullanılmıyor, çünkü anlamı ters çevirebilir: "offer the floor", "do not offer the floor" içinde geçer.
  3. Birden fazla adımda geçen kural global prompt'a bir kez taşınıyor.
- **Sert sınır:** Her aşamadan sonra yeniden render ve ölçüm yapılıyor. Hâlâ sert sınırın üstünde olan adım varsa build `SpecError` ile duruyor ("prompt budget exceeded … no policy rule is cut", adımlar ve token sayılarıyla). Hedef ile sınır arasında kalan adım için uyarı veriliyor.
- **Kapanış kuralları (önceden sessizce kayboluyordu, F-042):** `closing.rules` hiçbir prompt'a girmiyordu. Şimdi:
  - `closing_outcome` etiketli olanlar "kod" olarak yerleşiyor;
  - etiketsiz olanlar global prompt'a gidiyor.

### 3. Trace

`build.py` render özetine iki tür satır ekliyor; build hatayla dursa da (`finally`) yazılıyorlar.

- **`rule_placement:`** Her kural için bir satır, toplam spec kuralı kadar. Yeri ve nedeni:
  - `its section`;
  - `code: offer_amounts`;
  - `duplicate of offer.rules[9] (step negotiate)`;
  - `moved: was in confirm_record, identity`;
  - `closing rule, not guaranteed by code`.

  Etiketli bir kural prompt'ta kaldıysa nedeni de yazıyor: "kept: within budget" ya da "this spec has no data for that check".
- **`budget:`** Değişen ya da hedefi aşan her adım için `~önce -> ~sonra tokens (target, limit)` ve çalışan aşamaların listesi.

## Sonuçlar (offline render)

| Spec | Etiket | En büyük adım (önce → sonra) | Sonuç |
|---|---|---|---|
| Fixture A/B (elle yazılmış) | yok | koruma devreye girmiyor | değişiklik yok |
| Brief A, canlı f040 | yok | negotiate 1405 → 1350 (yalnız kopya) | geçer, uyarı |
| raw-a, canlı f040 | yok | negotiate 1481 → 1429 | geçer, uyarı |
| changed-a, canlı f040 | yok | hepsi hedefin altında | geçer |
| **Brief A+B, canlı f040** | **yok** | negotiate 1680 → **1596** | **build durur (açık hata)** |
| Brief A+B, etiketli kopya | var | negotiate 1595 → **1314**; diğerleri ≤ 1109 | geçer, uyarı |

**"Önce" sayıları neden eskisinden büyük:** Eskiden kaybolan etiketsiz kapanış kuralları artık global prompt'ta. Canlı A+B'de 8 kapanış kuralı var; etiket olmadan hepsi global prompt'a gidiyor.

**Etiketli kopya:** `tests/fixtures/extract/brief-ab-extracted-tagged.json` canlı A+B spec'inin kopyası (`brief-ab-extracted.json`). Etiketleri yeni extraction prompt'unun isteyeceği gibi **elle** koydum; yalnızca kodun gerçekten garanti ettiği 14 kurala:

- iş günü ve tatil;
- son tarih ve "son tarihten sonrası için son tarihi öner";
- "next/this <weekday>";
- tutar aralığı ve tabanın altı;
- kimlik deneme sayımı;
- tek ve son `close_call`, önce veda, transferin sözü geçmesi, en az bir söz varsa `promise`.

Bunlar etiketsiz bırakıldı, çünkü kod garanti etmiyor:

- "her ürün paid notluysa paid";
- "ilk paid olmayan notun reason'ı";
- "transferde not ekleme";
- "kayıt iki kez başarısız olursa not ekle".

## Kararınız gereken noktalar

1. **Hedef 1200 ile dürüst etiketler çakışıyor (A+B `negotiate` ~1314).** Kalan içerik konuşma kuralları: borcu söyleme, ikna denemeleri, belirsiz tarih, zorluk durumu, çok ürün. Seçenekler:
   - (a) Hedef 1200'de kalsın; 1200–1500 arası yalnızca uyarı, sınır 1500. Şu anki davranış bu.
   - (b) Hedef yaklaşık 1350'ye çıksın.
   - (c) Sabit `NEGOTIATION_TASK_TEMPLATE` metni kısaltılsın (~150 token kazanç; ama ifadeleri chat testleriyle oturmuş, risk var).
   - (d) Çok ürün kuralları yalnızca birden çok ürün olduğunda gösterilsin. Bu çalışma anı bilgisi; şablon değişikliği gerekir.

   Önerim (a) + (c)'nin küçük bir sürümü, chat testiyle birlikte.
2. **Etiketsiz bir A+B çıkarması artık build'i durduruyor.** Bu, görevin "sınırı aşarsa açık hata, kural kesme" kuralı. Yeni extraction prompt'u etiketleri istiyor. Model etiketlemezse A+B build'i durur; eskiden 1498'de geçiyordu, ama kapanış kuralları sessizce kayboluyordu. Canlı tekrarda ilk bakılacak şey `rule_placement` satırlarında kaç kuralın `code:` olduğu.
3. **İskelet açığı (F-042).** Brief B'nin kapanış önceliği ("hepsi paid ise paid", "ilk paid olmayan notun reason'ı") kapanış kodunda yok. Kurallar global prompt'ta, ama ajan kapanış sonucunu seçmiyor. Brief B senaryolarında yanlış outcome riski var; ayrı bir görev (workflow/closing kodu) gerekir.

## Canlı tekrar (CTO)

Komutlar değişmedi (T-006 ve `tests/briefs/README.md`). Bakılacaklar:

- trace'teki `budget:` satırları;
- `rule_placement` satırlarının sayısının spec kural sayısına eşit olması;
- kaç kuralın `code:` olduğu;
- `enforced_by` etiketlerinin yalnızca tarih, tutar, iş günü, gün okuma, kimlik sayımı ve kapanış kurallarında olması.

Yanlış etiket görürseniz (konuşma kuralının `code` olması) önce o etiketin anlamını prompt'ta daraltmak gerekir.

## Testler (`tests/test_prompt_budget.py`)

- **Etiketli A+B:** Her adım sert sınırın altında; yalnızca `negotiate` hedefin üstünde ve uyarı veriyor. Her spec kuralı tam bir kez yerleşiyor. Aşama satırı yazılıyor; `negotiate` 1595'ten 13xx'e iniyor.
- **Prompt dışında kalanlar:** Yalnızca etiketli (`code:`) ya da kopya kurallar dışarıda. Kopyanın aslı bir prompt'ta duruyor. Etiketli bir kuralın metni gerçekten prompt'ta yok; etiketsiz bir kapanış kuralı global prompt'ta.
- **Etiketsiz A+B:** Açık `SpecError` veriyor (adım ve token sayısıyla).
- **60 sentetik kural:** Koruma ve hata devreye giriyor; sınır yükseltilince uyarı ve bütçe satırı çıkıyor.
- **Küçük spec (fixture A):** Hiçbir şey değişmiyor.
- **Cümle düzeyi kopya:** "Offer the floor." korunuyor ("Do not offer the floor." onu silmiyor); "ask once!" kopya sayılıyor.
- **Paylaşılan kural:** İki adımda geçen kural global prompt'a bir kez taşınıyor.
- **Verisiz etiket:** `next_weekday = ask` iken `weekday_reading` etiketli kural prompt'ta kalıyor ve trace nedenini yazıyor.
- **Bilinmeyen etiket:** `SpecError`.
- **Kapanış kuralları:** `closing_outcome` etiketli kural prompt'a girmiyor; etiketsiz kural global prompt'ta.
