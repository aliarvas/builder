# F-053 / F-054 raporu: kontrol sonucu sabit cümleyle; takvimi kod hesaplıyor

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11

## Özet

- **Testler:** `python3 -m unittest` 272 testin hepsini geçiyor; 9'u yeni (`tests/test_offer_speech.py`). `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok. Brief değeri yok; takvim spec'in takvim verisinden ve `now`'dan geliyor.
- **Değişen dosyalar:**
  - Kod: `builder/offer_check.py`, `builder/workflow.py`, `builder/prompts.py`.
  - Testler: `tests/test_multi_step.py` (yedi beklenti, yeni metin ve akışa göre), `tests/test_offer_date_only.py` (iki beklenti).

## F-053: kontrol sonucu deterministik söyleniyor

**Akış:**

```
check_offer
  ├─ ready → confirm_record
  ├─ limit → closing
  └─ (diğer) → offer_say → negotiate
```

- **`offer_say`:** Code adımı, `on_enter: tts "{{offer_message}}"`. Bu, canlıda çalışan `closing_say` biçiminin aynısı.
- **`negotiate`:** `on_enter_first_entry_only: true`. İlk girişte konuşuyor (borcu bildiriyor); kontrol sonucundan sonra yeniden girişte konuşmuyor ve müşteriyi bekliyor. Model kontrol adımının "çağrısını" taklit edecek bir tur bulamıyor.
- **Mesajlar müşteriye söylenen cümleler oldu** (`OFFER_VERDICT_MESSAGES`). Önceki metinler ajana talimattı ("Offer [date] instead."); `tts` ile aynen söylenselerdi F-047 tekrar ederdi. Şimdi örneğin:
  - "That day is not a business day. The next possible day is Tuesday, 27 October. Would that work for you?"
  - "The latest date I can record for the credit card ending 0377 is Monday, 2 November. Would Monday, 2 November work for you?"
  - "Thank you, that works for the credit card ending 0377. Now let us look at the personal loan."
- **Değerler konuşma dilinde:** tarih "Tuesday, 27 October", tutar "28.50" ya da "95"; ürün müşteriye görünen adıyla. `amount_missing` tutarı yeniden öneriyor ("Could you pay 95?"): tam tutar ya da önerilmişse taban.
- **Onayda değişiklik:** Onay adımındaki "değiştir" yolu artık sabit bir soruyla (`revise_ask`: "Of course. Which date or amount would you like instead?") `negotiate`'e dönüyor. `negotiate` yeniden girişte sustuğu için bu soru gerekli.
- **Negotiate prompt'u:** "Banka sistemi son kontrol sonucunu müşteriye zaten söyledi: tekrarlama; müşterinin sonraki cevabına yanıt ver."

## F-054: takvimi kod hesaplıyor

- **`offer_setup` yeni bir `calendar_text` değişkeni yazıyor:**
  - bugün;
  - bu haftanın kalan iş günleri;
  - gelecek haftanın iş günleri;
  - bu ve gelecek haftanın son iş günü.

  Hepsi konuşma dilinde ("Friday, 16 October"); tatiller ve iş günü kuralı spec'ten.

  Örnek (Çarşamba 14 Ekim): "Today is Wednesday, 14 October. Business days left this week: Wednesday, 14 October; Thursday, 15 October; Friday, 16 October. Business days next week: Monday, 19 October; … Friday, 23 October. Last business day of this week: Friday, 16 October. Last business day of next week: Friday, 23 October."
- **Ürün bilgileri:** Artık konuşma dilinde tarih ve tutar içeriyor: "latest date (deadline) Monday, 2 November; minimum amount 28.50; full amount 95". ISO tarih yok.
- **Negotiate prompt'u:** "Calendar, computed by the bank system: {{calendar_text}} … Use only the dates and amounts in the calendar and the account facts, in the same spoken form; never work out a date or an amount yourself." Böylece "son iş günü" gibi kurallar takvimden okunuyor, hesaplanmıyor.
- **Görevden bilinçli fark:** Görevde "son tarihe kadar" yazıyordu. Takvimi son tarihle kesmedim, çünkü son tarih ürüne göre değişiyor. Takvim ortak; her ürünün son tarihi ürün bilgilerinde. Sınırı zaten kod kontrol ediyor.

## Testler (`tests/test_offer_speech.py`)

- **Akış:** `check_offer` → `offer_say` (code + tts `{{offer_message}}`, passthrough) → `negotiate`. `negotiate` yalnızca ilk girişte konuşuyor; `revise_ask` sabit cümleli.
- **Mesajlar:** Bütün kontrol mesajları, yer tutucular doldurulunca, F-047 dedektörüne göre müşteriye söylenen konuşma.
- **PUB-07 senaryosu:** 26 Ekim tatil → "The next possible day is Tuesday, 27 October. Would that work for you?"
- **Ayrıntılar:** son tarih ve taban mesajları konuşma dilinde ve ürün adıyla; çok üründe sonraki ürün adıyla anılıyor.
- **Takvim:** 14 Ekim için tam metin doğru. 22 Ekim'de gelecek haftanın tatili (26 Ekim) listede yok. Ürün bilgilerinde ISO tarih yok.
- **Prompt:** `{{calendar_text}}` var, `{{today_text}}` yok; "never work out a date" ve "do not repeat it" kuralları var.

## Riskler ve notlar

1. **Sessiz yeniden giriş.** `negotiate` yeniden girişte konuşmadığı için diğer dönüşler de sessiz:
   - özel yolların `return`'ü (sabit cümleleri önce söyleniyor);
   - "önce yardım edeyim mi" sorusuna "evet" (`__previous__`).

   Bu ikinci durumda ajan müşterinin bir sonraki sözünü bekliyor. Canlıda müşteri sessiz kalırsa garip bir duraksama olabilir. Gerekirse o dönüş için de sabit bir cümle eklenebilir.
2. **Bütçe.** `negotiate` sürüm 11 spec'inde ~1205 token (hedef 1200; yalnızca uyarı), etiketli A+B'de ~1343. Tahmin, çalışma anında dolan `{{calendar_text}}` ve `{{products_facts}}` metinlerini içermiyor; bunlar birkaç yüz karakter ekler.
3. **Dil.** Mesajlar ve takvim İngilizce. Spec dili başka olsaydı bu sabit cümleler de çevrilmeliydi; şu an bütün brief'ler İngilizce.

## Canlı tekrar (CTO)

- **PUB-07:**
  - Tatil tarihine verilen cevap sabit cümleyle mi geliyor; `_call:` metni yok mu?
  - İlk ikna tarihi takvimdeki "last business day of this week" ile aynı mı (Friday, 16 October)?
- **Çok ürün:** İkinci ürün sabit cümleyle adıyla açılıyor mu?
- **Onay:** Müşteri onayda değişiklik isterse sabit soru geliyor mu?

## Fix (review F-053/054: ölü hava, `more` sorusu, çalışma anı metinleri)

**Bulgu 1: yeniden girişlerde ölü hava yok.**

- `negotiate` artık **her girişte konuşuyor** (`on_enter_first_entry_only` kaldırıldı).
- **Bekleme `negotiate`'in iki ikiziyle sağlanıyor:** `offer_say` ve `revise_ask` artık code adımı değil, `negotiate`'in kopyası olan konuşma adımları.
  - Prompt, geçişler ve extraction aynı; tek fark girişte sabit bir `tts` cümlesi (`{{offer_message}}` ya da "Of course. Which date or amount would you like instead?").
  - Cümleyi söyledikten sonra müşteriyi bekliyorlar.
- **Dönüşler:**
  - Bu adımlardan birinde tetiklenen bir yan soru (dolandırıcılık, robot, insan isteğinde "önce yardım edeyim mi → evet") `__previous__` ile döndüğünde adım cümlesini yeniden söylüyor. Bu bekleyen soru oluyor: "Would Tuesday, 27 October work for you?".
  - `negotiate`'e dönüşte model bekleyen soruyu tekrar soruyor.
  - Kaynak başına düğüm çoğaltmaya gerek kalmadı.
- **Aynı sorun açılışta da vardı:** Açılışta tetiklenen bir yan soru (örneğin "robot musun?") dönüşte susuyordu. `opening` artık her girişte konuşuyor. Prompt'a şu eklendi: "If you already gave the introduction in this call, do not repeat it: answer briefly and ask the question again." Tanıtım tek seferlik kalıyor (F-048); yeniden sorma `opening_reask` gibi kısa.
- **İkizler kaynak sayılıyor:** `STEP_ALIASES` güncellendi: `negotiate` → `negotiate`, `offer_say`, `revise_ask`. Özel yollar ikizlerde de tetikleniyor; `_done` dönüşleri ikizlere de gidebiliyor. Bütçe korumasında ikizler `negotiate` adımına bağlı.
- **Yeni genel test (`NoDeadAirTests`):** Bütün fixture'larda ve kayıtlı extraction spec'lerinde iki şey sınanıyor:
  - global yolların tetiklenebildiği her konuşma adımı girişte konuşuyor (`silent` değil, ilk-giriş bayrağı yok);
  - her `_done` dönüş hedefi girişte konuşuyor.

  Eski davranışta bu test kırılırdı.

**Bulgu 2: `ok` + `more` soruyla bitiyor.** "Thank you, that works for the credit card ending 0377. Now let us look at the personal loan. The amount due is 300. Could you pay 300?" Tutar sonraki ürünün tam tutarı ve kod tarafından konuyor.

**Bulgu 3: bütçe tahmini çalışma anı metinlerini içeriyor.**

- `workflow_prompt_estimates` artık prompt'taki çalışma anı değişkenleri için sabit bir pay ekliyor:
  - `{{calendar_text}}` 520 karakter;
  - `{{products_facts}}` 600 karakter (iki ürün);
  - `{{offers_summary}}` ve `{{offer_message}}` 160'ar karakter.
- Trace'teki `prompt_estimate` ve bütçe koruması aynı fonksiyonu kullanıyor.
- **Sonuç dürüst ama yüksek:**

| Spec | `negotiate` (çalışma anı dahil) | Durum |
|---|---|---|
| sürüm 11 Brief A | ~1547 | sert sınırın biraz üstü |
| etiketli A+B | ~1685 | sert sınırın üstü |

- Build durmuyor (T-009b): trace'te `budget_exceeded_but_shipped` ve son satır uyarısı çıkıyor.
- **Kısaltma önerisi:** Bu iki metnin kısaltılması bir sonraki adım olabilir. Takvim ürün son tarihinden sonraki günleri kesebilir; ürün bilgileri ham alanları ("type credit_card, card_last4 …") çıkarabilir.

**Testler:** `python3 -m unittest` 291 testin hepsini geçiyor. `docs/PROMPTS.md` yeniden üretildi. Güncellenen beklentiler:

- ikizlerin geçişleri `negotiate` ile aynı;
- model alanlı özel yolun `_done` dönüşleri ikizleri de içeriyor;
- açılış ilk-giriş bayrağı yok, prompt kuralı var;
- bütçe testleri çalışma anı payıyla.

**Not:** `test_callback`'ta bir ara kırılma görüldü; claude-dev2'nin süren işi, son koşuda geçiyor. claude-dev2'nin `callback.py` ve `third_party` kısmına dokunulmadı. Düzenlemeden önce `workflow.py` yeniden okundu; değişiklikler `negotiate`, `opening`, ikizler ve bütçe tahminiyle sınırlı.

Freya yok, commit yok, `env.sh` yok.
