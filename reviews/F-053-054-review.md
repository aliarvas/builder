# F-053 / F-054 review (kontrol sonucu sabit cümleyle, takvim kodla)

Rapor: tasks/F-053-054-report.md; bulgular docs/UAT-FINDINGS.md F-053, F-054. Kod düzenlemedim, Freya ve modele istek atmadım. `python3 -m unittest`: 272 test geçiyor. Üretilmiş kodu canlı Brief A spec'i (`traces/brief-a.spec.json`) ve Brief B fixture'ıyla çalıştırdım ve graf geçişlerini taradım (F-055 kapsamı dışında).

## Karar: düzeltme gerekli
Takvim hesabı, mesaj metinleri ve `offer_say` mekanizması doğru ve el hesabımla uyuşuyor. Ama `negotiate`'in `on_enter_first_entry_only` yapılması, kontrol sonucu dışındaki yeniden girişleri de sessiz bırakıyor: scam/robot/bilinmeyen-soru gibi global yolların ve Brief B'de ürün itirazının `negotiate`'e dönüşünde ajan konuşmadan bekliyor (bulgu 1). Kit, sessiz kalan simüle müşterinin telefonu kapattığını belirtiyor; sessizlik riski gerçek. Küçük, hedefli bir düzeltmedir.

## Bulgular

### 1. [Yüksek] Kontrol sonucu dışındaki yeniden girişler de sessiz: ölü hava
- Canlı Brief A spec'inde `negotiate`'e giren geçişler: `offer_setup` (ilk giriş, konuşur), `offer_say` ve `revise_ask` (ikisi de kendi sabit cümlesini söyledi, sonra beklemesi istenen bir akış), ve `__previous__` ile dönen global yollar: `special_human_request` (önce yardım edeyim mi → "evet" → dönüş), `special_hardship_support`, `special_scam_question`, `special_robot_question`, `special_unanswerable_question`. Brief B'de ayrıca `special_product_dispute_done` → `negotiate`.
- `negotiate` `on_enter_first_entry_only: true` ve `on_enter` yok (varsayılan llm); kit `workflow-format.md:164`: bayrak girişi yalnız ilk ziyarette çalıştırır; yeniden girişte düğüm kullanıcıyı bekler. Bu, T-005d'de açılış için de yazdığım ve o zaman ayrı bir `opening_reask` adımıyla çözülen sorun.
- Sonuç: müşteri "Is this a scam?" diyor → global yol sabit cümleyi söylüyor → `negotiate`'e dönüyor → ajan susuyor; bekleyen soru ("Can you make this payment today?") yeniden sorulmuyor. Aynı şey robot sorusu, "I don't have that information" yolu, insan isteği "evet" cevabı ve Brief B ürün itirazı sonrası için geçerli. Kit: sessiz kalan ajanda simüle müşteri kapatır. Bu sorular halka açık testlerde ve final müşteri tarzlarında (`asks_back`, `talkative`) sık.
- **Düzeltme:** dönüşü sessiz bırakma. İki seçenek: (a) yeniden giriş için ayrı bir `negotiate_resume` konuşma adımı (aynı prompt ve geçişler, `on_enter` llm: "bekleyen soruyu tek kısa cümleyle yeniden sor"); `__previous__` yerine kaynak adım `negotiate` ise bu adıma dön; Brief B'deki `special_product_dispute_done` da buna gitsin. (b) `offer_say`'in yaptığı gibi dönüşte sabit bir tts adımı: "Back to your payment: …" ama bekleyen soruyu bilmediği için (a) daha güvenli. Test: her global yol ve `_done` dönüşü, hedef olarak konuşan bir adıma gidiyor.

### 2. [Orta] `ok` + `more` mesajı soruyla bitmiyor
- Çok ürünlü akışta kabul sonrası söylenen sabit cümle: "Thank you, that works for the credit card ending 0377. Now let us look at the personal loan." Ardından `negotiate` susuyor. Cümle bir ifade; müşteri bir soru duymadığı için beklemede kalıyor. Diğer mesajlar ("…Would that work for you?", "Could you pay 540?", "On which day would you like to pay?") soruyla bitiyor, bu tek istisna.
- **Düzeltme:** `more` mesajına bir sonraki ürün için tam tutar sorusu ekle: "…Now the personal loan: the amount due is 540. Could you pay 540?" (`amount_missing` ile aynı kalıp, kod tutarı verir).

### 3. [Düşük] Bütçe tahmini çalışma anı metinlerini içermiyor
Rapor haklı: `{{calendar_text}}` (~450 karakter) ve `{{products_facts}}` tahmine girmiyor; `negotiate` etiketli A+B'de ~1343 + yaklaşık 150–300 token. Hedef üstü zaten uyarı; sert sınıra yakın değil, ama çok ürünlü (üç ürün) için `products_facts` büyür. İzde `prompt_estimate` yanında "runtime text ~N tokens" notu faydalı.

## Doğrulananlar

**`offer_say` akışı.** `check_offer`: `ready → confirm_record`, `limit → closing`, `always → offer_say`; `offer_say`: `code`, `on_enter: tts "{{offer_message}}"`, passthrough → `negotiate` (canlıda çalışan `closing_say` kalıbı). `negotiate` ilk girişte konuşuyor (borç bildirimi, `offer_setup`'tan); kontrol sonrası model araya girmiyor, böylece F-053'teki `_call:check_offer{…}` taklidi oluşamaz.

**Takvim, el hesabıyla (bugün Çarşamba 2026-10-14):** üretilen `calendar_text`: "Today is Wednesday, 14 October. Business days left this week: Wednesday, 14 October; Thursday, 15 October; Friday, 16 October. Business days next week: Monday, 19 October … Friday, 23 October. Last business day of this week: Friday, 16 October. Last business day of next week: Friday, 23 October." El hesabım: Çarşamba–Cuma kalan, 19–23 Ekim gelecek hafta, bu haftanın son iş günü Cuma 16 Ekim; **birebir**. Erken bant ürün bilgisi: "latest date (deadline) Monday, 2 November; minimum amount 180; full amount 540" (12. iş günü, 26 Ekim tatili atlanarak = 2 Kasım: doğru). Başka gün (22 Ekim, Perşembe): gelecek hafta listesi 26 Ekim'i (tatil) atlayıp Salı 27'den başlıyor, bu hafta son iş günü Cuma 23, gelecek hafta Cuma 30: doğru. ISO tarih ürün bilgisinde yok.

**Mesajlar (PUB-07 senaryosu ve diğerleri), müşteriye söylenen doğal cümleler:**
- 26 Ekim → "That day is not a business day. The next possible day is Tuesday, 27 October. Would that work for you?"
- 10 Kasım → "The latest date I can record for the personal loan is Monday, 2 November. Would Monday, 2 November work for you?"
- tutar 100 → "The lowest amount I can record for the personal loan is 180. Could you pay 180?"; 700 → "The amount due on the personal loan is 540. Could you pay 540?"; tür `other` sayısız → "Could you pay 540?" (ajan "ne kadar" diye sormuyor)
- tarih anlaşılmadı → "Sorry, I did not catch the date. On which day would you like to pay?"; çok erken tarih → "I can only record a date from Wednesday, 14 October. Would … work for you?"; kabul → "Thank you, that works for the personal loan."
Hepsi ürün adıyla, konuşma dilinde tarih/tutarla; yer tutucular doldurulunca F-047 dedektöründen geçiyor (rapor testi).

**Prompt yalnız verilen tarihleri kullandırıyor:** negotiate görevi `{{calendar_text}}` içeriyor, `{{today_text}}` yok; "Use only the dates and amounts in the calendar and the account facts, in the same spoken form; never work out a date or an amount yourself" ve "The bank system already told the customer the last check result: do not repeat it" var. Persuasion kuralları ("last business day of this week") takvimdeki hazır satırı kullanabiliyor.

**Onayda değişiklik:** `confirm_record` "değiştir" yolu `revise_ask` (sabit soru) ile `negotiate`'e dönüyor; bu yolda soru önce söylendiği için sessizlik yok.

## Kurallar
Brief değeri yok; takvim spec'in takvim verisi ve `now`'dan; mesajlar genel İngilizce (dil notu rapordaki gibi); Freya/model isteği yok. UAT'ta F-053/F-054 durumları "fixed offline, retest pending" olmalı (PUB-07 v13 ledger geçti, bu değişiklikler canlıda denenmedi).

## Canlı doğrulama için
Rapordaki liste doğru; ek olarak PUB-07'de ilk ikna tarihi "Friday, 16 October" mi ve müşteri "Is this a scam?" / "Are you a robot?" dedikten sonra ajan bekleyen soruyu sürdürüyor mu (bulgu 1).


---

## Re-review (fix for findings 1–3)

**Method:** offline. I read the new graph (twins, transitions, global nodes), ran `Call` simulations from `tests/test_offer_date_only.py`, measured the real size of the runtime texts, ran `python3 -m unittest` (291 OK). No Freya, no model, no edits. claude-dev2's F-055 work (`callback.py`, `third_party`) was not reviewed here.

### Decision: **merge edilebilir** (two LOW notes)

### Finding 1 (dead air) — fixed, with a better design than I proposed

- `negotiate` now speaks on **every** entry (`on_enter_first_entry_only` removed, `on_enter` is the default llm). A `__previous__` return from `special_human_request`, `special_hardship_support`, `special_scam_question`, `special_robot_question`, `special_unanswerable_question` or `special_product_dispute_done` lands on a speaking step, so no silence.
- `offer_say` and `revise_ask` are now **conversation twins** of `negotiate`: I compared them in the rendered graph and `task_message`, `extraction_schema`, `tools` and `transitions` (`check_offer`, `confirm_record`, `closing`) are identical; only `on_enter` differs (`tts {{offer_message}}`, and the fixed revise line). So after the fixed line the engine waits for the customer, and a side question that returns by `__previous__` re-enters the twin and **says the pending question again** ("Would Tuesday, 27 October work for you?"). That is what the customer needs to hear.
- Entry paths checked: `offer_setup → negotiate` (first entry only, the model speaks), `check_offer → offer_say` (always), `confirm_record → revise_ask` (on revise). No code step goes straight to `negotiate` except `offer_setup`.
- Global paths can fire from the twins: `excluded_nodes` lists neither twin, and `STEP_ALIASES` maps `negotiate → negotiate, offer_say, revise_ask`, so rule placement and the budget guard treat the three as one step.
- `opening` also speaks on every entry now, with the prompt line "If you already gave the introduction in this call, do not repeat it". Consistent with F-048 (introduction only once). The new `NoDeadAirTests` checks both properties on all fixtures; it would have failed on the old behavior.

### Finding 2 (`ok` + `more` without a question) — fixed

Message now: "Thank you, that works for the credit card ending 0377. Now let us look at the personal loan. The amount due is 300. Could you pay 300?" It ends with `?`, names the next product, and the amount comes from code (full amount of the next product). State after the turn is consistent: `offer_proposed_kind = full`, `offer_amount` and `offer_date` cleared, `offers_accepted_count = 1`, so "yes" accepts the proposed 300 (F-052 path). No invented value.

### Finding 3 (budget estimate) — fixed, honest

`workflow_prompt_estimates` adds a fixed share for `{{calendar_text}}` (520 chars), `{{products_facts}}` (600), `{{offers_summary}}`/`{{offer_message}}` (160 each). I measured the real text for the fixture: calendar 361 chars, product facts 266 + 246 per extra product (266 / 512 / 758 for 1 / 2 / 3 products). So the estimate is conservative for one or two products. The reported `negotiate` figures (~1547 and ~1685) are therefore about 1485 real tokens for two products on the version 11 spec; the A+B tagged spec is still above 1500. The build does not stop (`budget_exceeded_but_shipped`, T-009b) and the trace says so. That is honest.

### Notes (LOW, no blocker)

1. **Three products:** facts reach ~758 chars, 158 more than the 600 share (about +40 tokens not counted). Use a per-product share (about 250 chars × number of products from the account) or compute the bound from the spec's product count if known; otherwise leave the constant and accept ~40 tokens of error.
2. **Over the hard limit on the A+B spec** is the real cost of the new prompt. The developer's idea (cut the calendar after the last deadline, drop raw field names such as `card_last4 …` from the facts line) is good; the raw `type credit_card, … days_late 4` prefix is in the prompt but the next line already has the spoken form, so removing it saves about 90 chars per product with no loss. Worth doing before the live run, not before merge.

### UAT status

F-053 and F-054: "fixed offline, retest pending". In the live retest also check: (a) "Is this a scam?" and "Are you a robot?" after an offered date, then the agent repeats the pending question once and does not speak a second time on top of it; (b) the first customer answer after `offer_say` is routed (no extra model sentence before it).
