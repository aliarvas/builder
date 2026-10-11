# F-061 / F-062 raporu: söz olmayan ürünlere kod sahipli not; ürün başına ret

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11 · **Kaynak:** `tasks/MULTI-READY-report.md` bulgu 1–2

## Tasarım notu (uygulamadan önce)

Hepsi spec verisinden. Bir alan yoksa davranış bugünküyle aynı; Fixture A'da hiçbiri yok, bu yüzden Brief A değişmiyor.

**(a) Spec (yeni, isteğe bağlı alanlar):**

- **`closing.product_notes`:** Söz olmayan her ürün için not kuralı.

  ```
  {tool, product_field, reason_field, reasons[], refused_reason, failed_reason, skip_outcomes[]}
  ```

  - `reasons`: brief'in izin verdiği neden değerleri.
  - `refused_reason`: reddedilen ya da hiç anlaşılmayan ürün.
  - `failed_reason`: kaydı iki kez başarısız olan ürün.
  - `skip_outcomes`: bu sonuçlarla kapanan çağrıda hiç not yok (örneğin transfer).
  - **Doğrulama:** neden değerleri `reasons` içinde; `skip_outcomes` kapanış tablosunun sonuçlarından. Render'da: araç OpenAPI'de, alanlar aracın gövdesinde, nedenler aracın enum'unda.
- **`negotiation.product_end_values`** (`close_values`'un alt kümesi): Yalnız konuşulan ürünü bitiren ret; başka ürün kaldıysa çağrı sürer.
- **`negotiation.attempt_values`:** Bir ikna denemesi harcayan ret (yol `stay`).
- **`offer.persuasion_attempts`:** Ürün başına deneme sayısı, sıralı kurallar: `[{when?, value}]`. Biçim `max_rejected_offers_by_product` ile aynı.
- **Extraction:**
  - Akış grubunda niyetlere `per_product` (yol `end`) ve `uses_attempt` (yol `stay`) bayrakları;
  - teklif grubunda `persuasion_attempts`;
  - kapanış grubunda `product_notes`.
  - Hepsi prompt'ta tarif ediliyor ve kodla doğrulanıyor.
  - Brief "her ürüne not" diyor ama `product_notes` boş kalırsa kural `coverage.unmapped`'e düşer (mevcut mekanizma).

**(b) Ürün başına ret ve not durumu (kod):**

- `negotiate`'ten (ve ikizlerinden) `product_end_values` ya da `attempt_values` niyetiyle yeni kod adımı **`product_refusal`**'a gidiliyor. Konuşulan ürün, hesap sırasında henüz ele alınmamış ilk ürün.
- **Deneme niyeti ve spec deneme sayısı veriyorsa:**
  - deneme kaldıysa sayaç artıyor ve `negotiate`'e dönülüyor (model ikna ediyor; prompt hangi denemede olduğunu görüyor);
  - deneme kalmadıysa ürün bitiyor.
- **Ürün bitince:**
  1. Ürün `offers_noted`'a ve neden `product_note_reasons`'a (`refused_reason`) yazılıyor.
  2. Ürün kaldıysa `more` cümlesiyle `offer_say`'e gidiliyor; kabul varsa okumaya (`confirm_record`); yoksa kapanışa (`negotiation:<değer>`).

**(c) Not döngüsü (kapanıştan önce, sessiz):**

```
closing → note_next (kod) → note_record (api_request add_note, silent, passthrough) → note_next … → closing_say
```

- **`note_next`** hesap sırasıyla, kaydedilmemiş (`promises_recorded_numbers`, F-063) ve henüz notu olmayan (`notes_written`) ilk ürünü seçiyor.
- **Neden sırası:**
  1. Kaydı tükenmiş ürün (`promise_attempts_N` ≥ azami) → `failed_reason` (kural 11).
  2. Kodun yazdığı neden → o neden.
  3. Çağrının kapanış nedeni `reasons`'ta ise → o neden (örneğin `hardship`).
  4. Yoksa → `refused_reason`.
- **Atlama:** Çağrının sonucu `skip_outcomes`'ta ise (transfer) hiç not yok.
- **Başarısızlık:** Bir not bir kez yeniden deneniyor, sonra atlanıyor.
- **Özel yolun notu:** Modelin özel yolda yazdığı not (`*_done` adımı, `special_noted_code`) ve not aracıyla kapanan özel yolun notu `notes_written`'a giriyor; ikinci kez yazılmıyor.

**Koordinasyon (claude-dev2, F-063):**
- `confirm_record`, `record_*` ve `confirmation_progress` koduna dokunmuyorum; yalnızca onların yazdığı `promises_recorded_numbers` ve `promise_attempts_N` değerlerini okuyorum.
- `workflow.py`'de iki küçük kanca: `negotiate` geçişleri ve `closing` geçiş hedefi. Kod `builder/product_notes.py` ve `offer_check.py`'de.

## Uygulama

**Sonuç:**
- MULTI-READY'deki `expectedFailure` testi (`test_pub12_refused_products_are_noted`) artık normal bir test ve geçiyor. PUB-12 uçtan uca beklenen ledger'a ulaşıyor: söz p1 510 (15 Ekim), `refused` notu p2 ve p3, sonuç `promise`.
- `python3 -m unittest`: 373 test, OK. `docs/PROMPTS.md` yeniden üretildi.

**Değişen ve yeni dosyalar:**

| Dosya | Ne değişti |
|---|---|
| `builder/spec.py` | Yeni alanların doğrulaması (`_validate_product_intents`, `_validate_product_notes`, `offer.persuasion_attempts`) |
| `builder/offer_check.py` | `PRODUCT_REFUSAL_BODY`, `NOTE_NEXT_BODY`, durum değişkenleri. Sınırla kapanan ürüne `refused` nedeni yazılıyor; `more` sonraki ürünün deneme sayısını veriyor; özel yolun notu `notes_written`'a giriyor |
| `builder/product_notes.py` (yeni) | `product_refusal`, `note_next`, `note_record` adımları ve iki kanca |
| `builder/workflow.py` | Tek çağrı (`add_product_steps`), ikizler kopyalanmadan önce; bir import |
| `builder/prompts.py` | Extraction prompt'ları (akış: `per_product`/`uses_attempt`; teklif: `persuasion_attempts`; kapanış: `product_notes`), `PERSUASION_STATE_LINE`, `PRODUCT_INTENT_DESCRIPTION` |
| `builder/extract.py` | Birleştirme ve doğrulama (`_check_product_notes`, bayrak kontrolleri) |
| Fixture'lar | Fixture B (`product_notes`, `product_end_values`, kaynak alıntısıyla); etiketli A+B (aynısı ve bant başına `persuasion_attempts`, elle, provenance'ta işaretli). Fixture A ve sentetik değişmedi |
| Testler | Yeni `tests/test_product_notes.py` (12 test); `tests/test_multi_ready.py` (PUB-12 testleri yeni davranışa göre, not döngüsü simülasyonu); `tests/test_multi_step.py` (kapanış yolu testi not döngüsünü tanıyor; sızıntı testinde `product_notes.py` için `"type"` izni); `tests/test_extract.py` (4 yeni); `tests/extract_helpers.py` (bayraklar) |

**Davranış:**

- **Ürün reddi (F-062):**
  - **Etiketli A+B:** `refusal_attempts_left` deneme harcıyor; ürün bandına göre kredi 2, araç kredisi 1. Deneme kalmadıysa ya da niyet `refused_attempts_exhausted` ise ürün `refused` olarak kapanıyor.
  - **Ürün kapandıktan sonra:** Ürün kaldıysa sabit `more` cümlesi (`offer_say`), kabul varsa okuma, yoksa kapanış (`negotiation:<değer>`).
  - **Prompt:** Deneme sayısı prompt'ta görünüyor ("Persuasion attempt … counted by the bank system: 1").
  - **Fixture B:** Deneme verisi yok; `no_arrangement` ürünü hemen kapatıyor.
- **Not döngüsü (F-061):**
  - Kapanış sonucundan sonra ve vedadan önce, sessiz.
  - Neden sırası: kaydı tükenmiş → `failed_reason`; kodun yazdığı → o; kapanış nedeni listede → o; yoksa `refused_reason`.
  - Transferde (`skip_outcomes`) hiç not yok.
  - Başarısız not bir kez yeniden deneniyor, sonra atlanıyor.
- **Testlerin kanıtladığı:**
  - PUB-12;
  - söz hiç yokken üç ürün `refused` ve sonuç `no_promise/refused`;
  - kural 11: üçüncü ürünün kaydı iki kez başarısız → yalnızca o ürüne `service_error`;
  - transferde not yok;
  - özel yolla (dispute) not edilmiş ürün tekrarlanmıyor;
  - `hardship_declined` ürünü numarasıyla not edince o ürün tekrarlanmıyor ve diğerleri `hardship` alıyor.
- **Yapı (bütün fixture'lar ve A+B spec'leri):**
  - Yeni adımlar yalnızca spec isterse var;
  - `note_record` sessiz, passthrough bir `api_request`, son geçişi `always`, `tts` yok;
  - gövde yalnızca koddan dolan alanlar taşıyor: model alanı `text` çıkarıldı;
  - `negotiate`, `offer_say` ve `revise_ask` aynı ret geçişini taşıyor.
- **Brief A:**
  - Fixture A'da yeni adım yok;
  - `negotiate` geçişleri `check_offer`, `confirm_record`, `closing` ve deneme satırı yok;
  - `closing` → `closing_say`;
  - bütçe tahmini aynı (726; sürüm 11 1437).

**Extraction:**
- Yeni alanlar prompt'ta tarif ediliyor ve kodla doğrulanıyor:
  - not aracı ve alanları sözleşmede;
  - nedenler aracın enum'unda;
  - `refused_reason`/`failed_reason` nedenlerde;
  - `skip_outcomes` kapanış tablosunda;
  - kaynak alıntısı zorunlu;
  - `per_product` yalnızca `end`, `uses_attempt` yalnızca `stay` ile ve bir `per_product` değeri gerektiriyor.
- Hatalar onarıma gidiyor (testli).
- Brief A'da `product_notes` yok (test).
- **Coverage:** `closing.product_notes` ve `offer.persuasion_attempts` yolları çözülüyor. Alan çıkarılmazsa kural mevcut mekanizmayla `unmapped`'e düşüyor.

**Koordinasyon:**
- claude-dev2'nin F-063 kodlarına (`confirm_record`, `record_*`, `confirmation_progress`) dokunmadım. Not döngüsü onların `promises_recorded_numbers` ve `promise_attempts_N` değerlerini yalnızca okuyor.
- claude-dev2 bu arada `tests/test_multi_ready.py`'yi F-063'e göre güncellemişti. Onun `record_all`'ını koruyarak ortak bir `run_api` yardımcısına taşıdım; davranışı aynı.

## Riskler ve açık noktalar

1. **Eski canlı spec'ler:** `f040-b` ve `t006-brief-b` yeni alanları taşımıyor; eski yollar ve not yok (test `test_old_specs_without_the_new_fields_keep_the_old_routes`). Davranışın canlıda görünmesi için güncel prompt'larla taze bir A+B extraction'ı gerekiyor (canlı model çağrısı, CTO onayı).
2. **Bütçe:** Deneme satırı (~190 karakter) yüzünden etiketli A+B'de `negotiate` 1575'ten **1627**'ye çıktı. Build durmuyor, uyarıyla gönderiliyor. Brief A'ya etkisi yok.
3. **[HYPOTHESIS] Deneme sayımı:** "Her ret bir deneme harcar; deneme kalmadıysa bir sonraki ret ürünü kapatır" diye yorumlandı. Örneğin kredide üç ret: iki ikna, sonra kapanış. Brief A kural 30–31'in okunuşu bu; canlıda doğrulanmalı.
4. **Taze Brief A extraction'ı:** Brief A'nın tablosundaki deneme sayısı da `persuasion_attempts`'e çıkabilir. O zaman tek ürünlü A'da da denemeleri kod sayar; sonuç aynı (kapanış `no_promise/refused`), mekanik farklı.
5. **Kural 11 ve kayıt döngüsü (F-063, claude-dev2):** `confirmation_progress` bir ürün tükenince (`exhausted`) doğrudan kapanışa gidiyor. O ürünün arkasındaki kabul edilmiş ama kaydedilmemiş ürünler kaydedilmiyor ve not döngüsünde `refused` alıyor. Brief "keep the promises that were recorded" diyor; kalan ürünlerin kaydının denenmesi gerekip gerekmediği F-063'ün kararı.
6. **Kapanma (hangup):** Çağrı kapanış zincirinden önce biterse not döngüsü çalışmıyor (end-of-call close yalnızca `close_call`).
7. **Bulunmayan kural:** Brief B'nin "söz yoksa ilk notu `paid` olmayan ürünün nedeniyle kapat" kuralı not durumundan beslenebilir, ama kapanış tablosu bu görevde değişmedi. Örneğin ürün 1 `dispute`, ürün 2 `refused` iken nedenin `dispute` olması gerekir. Bugün `refused` çıkar. Ayrı bir küçük iş olarak öneriyorum.

**UAT:** `docs/` dışında kaldım. Önerilen durum: "F-061, F-062: fixed offline, retest pending (fresh A+B extraction, PUB-12)".

Freya yok, commit yok, `env.sh` yok.

## Fix (review F-061/062)

**(1) Kayıt döngüsü tükenen üründe durmuyor; kaydedilmemiş ürün hiçbir zaman `refused` değil.**
- **`confirmation_progress`** (`workflow.py`, F-063 kodu; claude-dev2 boştayken değiştirildi):
  - Denemesi biten ürün `promises_failed_numbers`'a yazılıyor ve döngü sürüyor.
  - Bekleyen kabul edilmiş ürün kalmayınca durum `complete` (hepsi kayıtlı) ya da `exhausted` (en az biri başarısız) oluyor.
  - `offers_accepted` yoksa eski sayı kuralına geri düşüyor.
- **`record_next`** (`record_loop.py`): Kenara konan ürünleri atlıyor. Modül docstring'indeki "ilk tükenen üründe dur" kararı bu yeni kararla değiştirildi.
- **Kapanış cümlesi:** Kapanış durumu yine `promise_failed`. Kayıtlı bir söz olduğunda `promise` satırı kazanıyor ve önce "I am sorry, I could not record every promise." söyleniyor. Seçim kuralı değişmedi.
- **Not döngüsü:** Kabul edilmiş ama kaydedilmemiş her ürün, denemesi bitmiş ya da hiç ulaşılmamış olsun, `failed_reason` alıyor.
- **Testler (`tests/test_record_loop.py`, claude-dev2'nin testi yeni karara göre):**
  - 3 kabul, p2 iki kez başarısız (çağrılar `p1, p2, p2, p3`) → p1 ve p3 kayıtlı, kapanış durumu `promise_failed`, sonuç `promise`, cümle "not every promise" ile başlıyor, notlar yalnızca `p2 service_error`, `refused` yok. Etiketli A+B ve Fixture B'de.
  - Son ürün başarısız olunca döngü bitiyor (`exhausted`).

**(2) İsteğe bağlı blok render'da ya da son turda geçersizse düşürülüyor; build sürüyor.**
- **Render:** `note_tool` `SpecError` verirse (araç yok, alan yok, enum dışı neden, kodun dolduramadığı zorunlu alan) `product_notes` düşüyor ve trace'e `warning: closing.product_notes dropped (F-061 not applied): …` yazılıyor. `closing` → `closing_say` kalıyor; ürün reddi adımı kalıyor.
- **Extraction:**
  - Erken turlarda bu bloklardaki hatalar onarıma gidiyor; buna dry render'da düşen not bloğu da dahil.
  - Son turda blok düşürülüyor ve `extract_warning` satırı yazılıyor: "…; optional block <ad> dropped".
  - Bloklar: `product_notes`, `persuasion_attempts`, `intent_flags`. Bayraklar düşerse deneme sayısı da düşüyor, çünkü onlara bağlı.
- **Testler:**
  - Not aracı hatalarında render düşürüp uyarı veriyor.
  - Extraction'da not bloğu hataları ve bayrak hataları önce onarıma gidiyor, sonra düşüyor; diğer bloklar kalıyor.

**(3) `persuasion_attempts` kanıtı.**
- Her `value` pozitif bir tam sayı olmalı ve belgede rakam ya da sözcük olarak yazılı olmalı (`count_written`; madde numaraları ve kural referansları sayılmıyor).
- Liste için `sources["offer.persuasion_attempts"]` alıntısı zorunlu. Teklif prompt'u zaten her alan için kaynak istiyor.
- Ayrıca liste doluyken `uses_attempt` niyeti zorunlu (gruplar arası kontrol).
- **Test:** Doğru liste ve kaynak geçiyor; 97 (belgede yok) ve kaynaksız liste önce onarıma gidiyor, sonra blok düşüyor.

**(4) Müşterinin andığı ürün:** `offer_product_number` ele alınmamış bir ürünü gösteriyorsa ret o ürüne yazılıyor. Gösterdiği ürün zaten ele alınmışsa hesap sırasındaki ilk açık ürün seçiliyor. **Testler:** kart kabul, müşteri araç kredisini (3) reddediyor → 3 `refused`, sonraki cümle krediyi (2) açıyor. Ele alınmış numara verilince 2 seçiliyor.

**(5) Eşleşen kural yok:** Ürüne uyan bir `persuasion_attempts` kuralı yoksa (bant boşluğu) ürün hemen kapanıyor. **Test:** Yalnız erken bant kuralı varken kredi (16 gün) ilk retle kapanıyor; araç kredisi (erken bant) bir deneme alıyor.

**Sonuç:** `python3 -m unittest` 378 test, OK. `docs/PROMPTS.md` güncel (prompt metni bu düzeltmede değişmedi). Bütçe değişmedi (etiketli A+B'de `negotiate` 1627, Brief A 726/1437).

**Canlı kontrol notları (review 6–7):**
- **Taze Brief A extraction'ı (6):**
  - `persuasion_attempts` (tablodaki 1 ve 2) ve bayraklar çıkıyor mu, kaynaklarıyla mı?
  - Çıkarsa tek ürünlü A'da denemeleri kod sayar. PUB-04–06 tipi retlerde sonuç `no_promise/refused` kalmalı.
  - İkna sırası (deneme 1: son iş günü ve tam tutar; deneme 2: geç bantta taban ve son tarih) prompt'taki deneme satırıyla tutarlı mı?
- **Uzun zincir (7):**
  - Kayıt ve not zincirleri tek kapanış turunda üst üste çalışıyor: 3 ürün için en fazla 6 kayıt adımı (yeniden denemelerle) ve 6 not adımı, ardından `closing_say`.
  - Hepsi sessiz ve passthrough; tek konuşulan mesaj `closing_sentence`.
  - Canlıda bakılacaklar: zincir 502 ya da geri alma vermeden tamamlanıyor mu, trace'te not çağrılarının sırası ve gövdesi doğru mu (`reason` enum'u şablon varsayılanla dolu mu)?
- **Kayıt hatası (bulgu 1):** Çok üründe bir kayıt hatası: sonraki ürün yine kaydediliyor mu, ledger'da yalnız `service_error` notu var mı?

Freya yok, commit yok, `env.sh` yok.
