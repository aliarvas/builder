# T-009c raporu: çalışma anı metinlerini kısaltma (bütçe)

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11 · **Kaynak:** `reviews/F-053-054-review.md` Notes 1–2

## Özet

- **Testler:** `python3 -m unittest` 320 testin hepsini geçiyor. 8'i yeni, hepsi `tests/test_offer_speech.py`'de. `docs/PROMPTS.md` yeniden üretildi.
- **Hedef tutmadı:** Etiketli A+B'de `negotiate` 1685'ten **1575'e** indi. 1500 hedefi 3 ürünlük dürüst payla tutmuyor; sayılar ve seçenekler aşağıda.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok, brief değeri yok.
- **Değişen dosyalar:**
  - Kod: `builder/offer_check.py`, `builder/prompts.py` (yalnız `NEGOTIATION_TASK_TEMPLATE`), `builder/workflow.py` (yalnız bütçe tahmini ve bir import satırı).
  - Testler: `tests/test_offer_speech.py`, `tests/test_multi_step.py` (iki beklenti), `tests/test_spoken_output.py` (bir beklenti).
- **claude-dev2:** `callback.py`'ye, `third_party` kısmına ve `prompts.py`'deki callback sabitlerine dokunmadım. Düzenlemeden önce dosyaları yeniden okudum. Bir ara onun yarım değişikliği yüzünden import hatası görüldü; bir sonraki koşuda düzeldi.

## (a) Ürün bilgilerinde ham alan öneki yok

Önce:

```
Product 1: type credit_card, card_last4 0377, past_due 95, days_late 4, minimum_payment 28.5. Earliest date …; latest date (deadline) …; minimum amount 28.50; full amount 95. Name it to the customer as: credit card ending 0377.
```

Şimdi:

```
Product 1, credit card ending 0377 (days late 4): deadline Monday, 2 November; minimum amount 28.50; full amount 95.
```

- **Görevden bilinçli fark: hangi alanların çıktığı.** Ham alanları tümden silmek politika bilgisi kaybettiriyordu. A+B kuralı şöyle: "For each product, state the past-due amount and how many days late it is." `days_late` başka hiçbir yerde söylenmiyor.
  - **Çıkan alanlar:** ürün adının ya da tutar sınırlarının zaten söylediği alanlar. Bunlar `id`, tür, etiket ve `min_amount`/`max_amount` kurallarının alanları (`past_due`, `minimum_payment`, `instalment_amount`).
  - **Kalan alanlar:** başka yerde söylenmeyen düz alanlar, konuşma biçiminde ("days late 4").
  - Kural spec'ten türetiliyor; hiçbir alan adı kodda yazılı değil.
- **En erken tarih ürün satırından takvime taşındı.** Ürüne göre değişmiyor; her satırda tekrar ediyordu.
- "latest date (deadline)" yerine yalnız "deadline" yazıyor; kurallar da bu sözcüğü kullanıyor.

## (b) Takvim kısaldı, hesaplar değişmedi

```
Today is Wednesday, 14 October. Business days this week: Wednesday 14, Thursday 15 and Friday 16 October. Business days next week: Monday 19, Tuesday 20, Wednesday 21, Thursday 22 and Friday 23 October. Last business day: this week Friday, 16 October; next week Friday, 23 October.
```

- **Aya göre gruplama:** Ay adı her gün için değil, her ay için bir kez yazılıyor. Bu metin 361 karakterden 281'e indi.
- **Kesme:** Yalnız kodun kabul edebileceği günler listeleniyor: en erken tarihten, ürünlerin **en geç** son tarihine kadar.
  - Kesme olursa "No day after Wednesday, 21 October can be recorded." satırı ekleniyor.
  - En erken tarih bugünden sonraysa "Earliest date: …" satırı ekleniyor.
  - Bir ürünün son tarihi yoksa ya da ürünler okunamıyorsa kesme yok.
- **Politika bilgisi:** "Last business day" satırı, o gün listelendiği sürece kalıyor (ikna kuralı "last business day of this week" için).
- **Kontroller aynı:** `offer_check` hesapları değişmedi; takvim yalnızca gösterim. Test: kesilmiş bir gün yine `date_too_late` ve doğru son tarihi alıyor.
- **A+B için sınır:** Gerçek A+B vakalarında takvim kesilmiyor, çünkü en geç son tarih 12 iş günü, yani iki haftadan uzun. Bu yüzden A+B'de kazanç gruplamadan geliyor.

## (c) Bütçe payı ürün başına

- **Paylar:** `RUNTIME_TEXT_CHARACTERS` artık her değişken için (sabit pay, ürün başına pay) taşıyor:

  | Değişken | Pay | Ölçülen en uzun |
  |---|---|---|
  | takvim | 340 sabit | 322 (iki yılın her günü) |
  | ürün bilgileri | ürün başına 140 | 138 |
  | kabul özeti | ürün başına 80 | |
  | kontrol mesajı | 150 sabit | |

- **Ürün sayısı:** Build anında bilinmiyor. Tahmin `ESTIMATED_PRODUCTS = 3` ile yapılıyor, çünkü kitteki en çok ürünlü vakalar (PUB-11, PUB-12) üç ürünlü.
- **Yer:** Sabitler metinleri yazan modülde, `offer_check.py`'de.
- **Kullanım:** `workflow_prompt_estimates(workflow, products=…)`; trace ve bütçe koruması aynı fonksiyonu kullanıyor.
- **Test (`RuntimeTextShareTests`):** Kodun yazdığı en uzun metinler paylara sığıyor: iki yıl boyunca her gün için takvim ve ürün satırları, her kontrol mesajı ve özet satırları. Tahmin ürün başına doğru artıyor.

## Ek: `negotiate` şablonu kısaldı

`NEGOTIATION_TASK_TEMPLATE`'te bütün kurallar duruyor; yalnızca tekrar eden ifadeler birleştirildi:

- "Calendar, computed by the bank system" yerine "Calendar";
- "in the calendar and the account facts, in the same spoken form" yerine "these dates and amounts";
- "raw account result" kaldırıldı, çünkü ürün bilgilerinde artık ham sonuç yok.

Şablon 1345 karakterden 1180'e indi. Testlerin sınadığı cümlelerin hepsi aynen duruyor.

## Ek bulgu ve düzeltme: sınır dolunca çelişen cümle

Pay testi bunu yakaladı. Geçersiz teklif sınırı dolunca ürün not ediliyor ve akış sonraki ürüne geçiyor (`more`). Ama `offer_say` cümlesi kapanan ürünü hâlâ öneriyordu:

> "The lowest amount I can record for the credit card ending 0377 is 28.50. Could you pay 28.50? Now let us look at the personal loan. The amount due is 300. Could you pay 300?"

Şimdi yalnızca "Now let us look at the personal loan. The amount due is 300. Could you pay 300?" söyleniyor. Kapanan ürünün önerilen tarih ve tutarı da siliniyor; böylece bir "yes" onu kabul etmiş sayılmıyor. Değişiklik `offer_check.py`'de üç satır ve testli (`ExhaustedProductMessageTests`). Bu kapsam dışıydı; reviewer isterse geri alınabilir.

## Sayılar (`negotiate`, çalışma anı dahil)

| Spec | Önce (F-053 Fix) | 1 ürün | 2 ürün | 3 ürün (varsayılan) |
|---|---|---|---|---|
| etiketli A+B | ~1685 | 1465 | 1520 | **1575** |
| sürüm 11 Brief A | ~1547 | 1327 | 1382 | 1437 |
| Fixture A | | 616 | 671 | 726 |

**Hedef tutmadı.** Etiketli A+B'de `negotiate` 3 ürün için 1575 token, hedef 1500. Kalan ~75 tokenın (~300 karakter) kaynağı çalışma anı metinleri değil:

- sabit `negotiate` metni: sistem prompt'u 1577 karakter, görev metni 3643 karakter;
- bunun ~2540 karakteri brief'ten gelen kurallar.

Build durmuyor; T-009b'deki gibi uyarıyla gönderiliyor.

**Karar sizin; seçenekler:**

1. **Payı 2 ürüne göre ayarlamak:** 1520 olur. Dürüst değil, çünkü kitte 3 ürünlü vaka var. Önermiyorum.
2. **Kodun zaten yaptığı kuralları etiketlemek:** Örneğin "Name each product in words: …" kuralını yeni bir etiketle (`product_naming`) kod tarafına almak, çünkü ürün adını kod yazıyor. Bu ~100 karakter kazandırır. Bu bir `spec.py` ve extraction değişikliği.
3. **Extraction prompt'u:** Neredeyse aynı kuralları birleştirmesini istemek. Örnekler: "Never ask the customer how much they can pay." ile "Never ask how much the customer can pay."; "Ask for the full past-due amount first." ile "Attempt 1: ask for the full past-due amount…".
4. **Sistem prompt'u:** Yalnız kimlik öncesine ait global kuralları (örneğin "before identity is verified") ilgili adımlara taşımak.

## Canlı tekrar (CTO)

- **PUB-11 / PUB-13:**
  - Ajan her ürünü adıyla ve "days late" bilgisiyle söylüyor mu?
  - Kimlik numarası, alan adı ya da "type credit_card" gibi bir metin müşteriye gidiyor mu?
  - İkna tarihi takvimdeki "Last business day: this week …" ile aynı mı?
- **PUB-12:** Reddedilen ürün sınırı doldurunca ajan doğrudan sonraki ürüne geçiyor mu, kapanan ürünü yeniden önermiyor mu?

## Fix (review T-009c: bulgu 1 ve 2)

**Bulgu 1: Sınırla kapanan üründen sonra önerilen tutar türü doğru.**
- `check_offer`'da `progress == 'more'` olduğunda `offer_proposed_kind` artık her zaman `full` oluyor.
  - Söylenen cümle her zaman sonraki ürünün tam tutarını öneriyor; durum artık bu cümleyle aynı.
  - Eskiden yalnız `ok` yolu sıfırlıyordu. Sınır yolunda `amount_too_low`'dan kalan `minimum` duruyordu.
- **Test:** İncelemedeki sıra (kart: `2026-11-30`, sonra `2026-10-16` ve tutar 1 → `more`; kredi: yalnız tarih `2026-10-20`) artık krediyi **300** ile kaydediyor; özet "personal loan: 300 on Tuesday, 20 October".
- **İncelemedeki ek öneri:** `more` olup sonraki ürün bulunamazsa (bugün mümkün değil) mesaj boş kalmıyor; ürün sorusu söyleniyor ("Which of your products is this payment for?"). Önerilen yer tutucusuz `more` metni yerine bunu seçtim, çünkü `more` metni sonraki ürün adı olmadan anlamlı bir cümle değil.

**Bulgu 2: Bool alanlar sözle yazılıyor.**
- Bir bayrak artık sessizce düşmüyor: `secured: true` → "secured yes", `disputed: false` → "disputed no".
- **Test:** "(days late 20, secured yes, disputed no)".

**Kapsam dışı bırakılanlar:**
- Bulgu 3 (`ESTIMATED_PRODUCTS` için `STARTER-KIT-FACTS.md` kaydı ve "yalnız tahminde kullanılıyor" testi) CTO talimatında yoktu; yapılmadı. `docs/` claude-dev2'de.
- Ürün payının fazladan alanlı ürünlerde ürün başına ~10 token eksik sayması (bulgu 2'nin ikinci maddesi) yalnız not olarak kaldı.

**UAT:** `docs/` dışında kaldım. Önerilen yeni kayıt: "stale proposed kind after a limit-closed product". Durum: fixed offline, retest pending (PUB-12).

**Testler:** `python3 -m unittest` 322 testin hepsini geçiyor; 2'si yeni (`tests/test_offer_speech.py`, `T009cFixTests`). Prompt metni değişmedi; `docs/PROMPTS.md` güncel.

Freya yok, commit yok, `env.sh` yok.
