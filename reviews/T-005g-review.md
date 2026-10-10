# T-005g review (offer.next_weekday, offer.max_rejected_offers_by_product)

Rapor: tasks/T-005g-report.md. Kod düzenlemedim, Freya'ya istek atmadım. `python3 -m unittest`: 140 test geçiyor. Kapsam: `spec.py`, `offer_check.py` ve ilgili fixture değerleri; extract.py bu review'a dahil değil. Yöntem: üretilen `offer_setup` / `check_offer` kodunu Brief A ve B fixture'larından kendim çalıştırdım (bugün Çarşamba 2026-10-14).

## Karar: düzeltme gerekli
`next_weekday` ve çok ürünlü sayaç mekanizması doğru ve geriye uyumlu. Ama Brief A fixture'ına yazılan `max_rejected_offers_by_product` değerleri (erken bant 1, geç bant 2) davranışı bozuyor: erken bantta tek bir kural dışı teklif çağrıyı hemen kapatıyor (bulgu 1). Mekanizma kalabilir; fixture değerleri ve anlam tanımı düzeltilmeli, sonra merge.

## Bulgular

### 1. [Yüksek] "Persuasion attempts" ile "reddedilen geçersiz teklif" aynı sayılmış; erken bantta ilk geçersiz teklif çağrıyı kapatıyor
- Fixture A: `max_rejected_offers_by_product = [{days_late 1–7 → 1}, {8–45 → 2}]`. Bu sayılar Brief A'nın "Persuasion attempts" sütunu (1 ve 2). Ama `check_offer` sayacı farklı bir şeyi sayıyor: kural dışı (tarih kuralı, tutar kuralı) *geçersiz teklifleri*. Brief A'da persuasion attempt, müşterinin "düz ret"i (kural 30) için; geçersiz teklif ayrı yol: tarih son tarihten sonraysa son tarihi öner, kabul etmezse ret (kural 23); tutar tabanın altındaysa tabanı bir kez öner (27).
- Kanıt (kendim çalıştırdım, kart, `days_late 4`, erken bant): müşteri son tarihten sonraki bir tarih söyleyince (`2026-12-30`, tutar 95) → `date_too_late`, `offer_progress = limit`, `offer_rejections = 1`. Yani çağrı hemen `offer_limit` ile kapanıyor (`no_promise/refused`); agent kural 23'ün gereği olan "son tarihi öner"i hiç yapamıyor. Aynı şey erken bantta fazla tutarda: `amount_too_high` → `limit`. Geç bantta (limit 2) ikinci geçersiz tekliften sonra kapanıyor (`rejected` sonra `limit`), yani bir öneri hakkı var.
- Önceki skaler değer (2, her iki bant) erken bantta bir geçersiz tekliften sonra counter-offer'a izin veriyordu; yeni değerler bunu geriletiyor. Chat/voice testinde "son tarihten sonrasını isteyen müşteri" vakası (A kural 23) erken bantta düşer.
- **Düzeltme:** mekanizmayı tutun, anlamı netleştirin: bu alan "kural dışı teklifler; counter-offer'a bir hak tanıdıktan sonra çağrı kapanır". Fixture A değerleri en az **2** olmalı (geçersiz teklif + reddedilen karşı öneri), yani "persuasion attempts + 1" ya da hiç by_product kuralı olmayıp skaler 2 kalmalı. Persuasion attempt sayacı (düz ret, kural 30) ayrı bir şey: zaten `negotiation` niyeti `refusal` + prompt tarafından yönetiliyor. Bu ayrım `spec.py` docstring'ine ve extraction prompt'una (F-040 kapsamında yeniden yazılacak `EXTRACT_OFFER_TASK`) yazılmalı; yoksa extractor "persuasion attempts" sayısını bu alana yazar ve yanlış değer brief'ten brief'e taşınır. (T-006b referans spec'leri de aynı yanlış anlamı taşıyor, bkz. T-006b review bulgu 1.)

### 2. [Orta] Bir ürünün limiti tüm çağrıyı kapatıyor
- `check_offer` `limit` döndürünce `workflow.py` `check_offer → closing` yolu çağrıyı `offer_limit` ile kapatıyor. Çok ürünlü Brief B'de bir ürünün limiti dolduğunda öteki ürünün kabul edilmiş ama henüz kaydedilmemiş teklifi kaybolur (`confirm_record` hiç çalışmaz, `promise_recorded_count` 0). Bu davranış ürün başına sayaç öncesinde de vardı (küresel sayaçla), ama artık "bu ürünün limiti doldu" bilgisi elimizde: o ürünü not düşülmüş/işlenmiş say (`offers_noted`'a ekle) ve diğer ürünlerle devam et; hiçbir ürün kalmadıysa kapat.
- Brief B kural 8–9 ürün başına ilerlemeyi ister. İlk Brief B chat testinden önce yapılmalı (kapsam dışı değilse bu görevde, değilse T-005h).

### 3. [Bilgi] Dönüş değerleri
- Bulgu 1 düzelince `rejected_offer_limit(product)` zaten `first_rule` ile ilk eşleşmeyi seçiyor; eşleşme yoksa skaler. Doğru. `product` değişkeni sayaç dalına girdiğinde her zaman atanmış (kontrol ettim: `product_unknown` ve `missing` bu dalı atlıyor).

## Doğrulananlar

**`next_weekday` (bugün Çarşamba 2026-10-14, A fixture'ı, 4 ilke):**

| İfade | following_week | upcoming | ask | alan yok |
|---|---|---|---|---|
| next Friday | **10-23** | **10-16** | `date_ambiguous` | `date_ambiguous` |
| next Wednesday | 10-21 | 10-21 | 10-21 | 10-21 |
| next Monday / next Tuesday | 10-19 / 10-20 | 10-19 / 10-20 | aynı | aynı |
| this Friday / this Wednesday | 10-16 / 10-14 | aynı | aynı | aynı |
| this Monday (geçmiş) | `date_too_early` | `date_too_early` | `date_too_early` | `date_too_early` |
| Friday / Friday next week | 10-16 / 10-23 | aynı | aynı | aynı |

El hesabıyla birebir: `following_week` = bir sonraki Pazartesi (10-19) + gün farkı; `upcoming` = sıradaki gelecek gün (`delta or 7`); `ask` = belirsiz kullanımda onay. İstenen örnek (next Friday: following_week 10-23, upcoming 10-16) doğru. Brief A kural 22 "next Friday said on a Friday = the Friday of the following week" ile `following_week` uyumlu.

- **Geriye uyum:** alan yoksa `data.setdefault("next_weekday", "ask")` ve `max_rejected_offers_by_product` yoksa `[]`; sentetik fixture yeni alanları taşımıyor ve eski davranışı veriyor (yukarıdaki "alan yok" sütunu). Geçersiz enum, negatif/sıfır limit, bilinmeyen anahtar `SpecError`.
- **`this <weekday>`:** artık her zaman bu takvim haftasının günü (`this_monday + weekday`); geçmişte kalan `date_too_early` oluyor (önceden sıradaki gelecek günü veriyordu). Brief A kural 22 ile uyumlu; bu bir davranış değişikliği, haberiniz olsun.
- **Çok ürünlü sayaçlar:** sayaçlar ve son imzalar ürün numarasına göre `offer_rejections_by_product` / `offer_last_signatures_by_product` içinde JSON olarak tutuluyor. Denedim: ürün 2'de bir ret, ürün 1'in sayacını artırmıyor; ürün 1'de ret ayrı sayılıyor; aynı teklifin tekrarı sayacı artırmıyor (imza aynı); eski `offer_rejections` değişkeni mevcut ürünün son durumunu gösteriyor.
- **Hardcode:** yok. Builder kodunda `days_late`, bant sınırı veya sayı yok (taradım); değerler fixture/spec verisi, kodda yalnızca alan ve enum adları (`following_week`, `upcoming`, `ask`) var. Sentetik fixture farklı davranışı test ediyor.

## Kurallara uyum
Freya isteği yok, stdlib, testler çevrimdışı.

---

# Fix kontrolü (bulgu 1 ve 2; rapor: tasks/T-005g-report.md "Fix — review düzeltmeleri")

Kod değiştirmedim, Freya'ya istek atmadım. `python3 -m unittest`: 142 test geçiyor. Üretilen `offer_setup` / `check_offer` kodunu A ve B fixture'larından kendim çalıştırdım (bugün Çarşamba 2026-10-14; `account_response.*` biçiminde ürünler).

## Karar: merge edilebilir
Bulgu 1 ve 2 kapandı. Bir bilgi notu (aşağıda, "Not düşülen ürün") sonraki işe kalıyor.

## Bulgu 1: kapandı (invalid offer ile persuasion ayrımı, en az 2)
- `spec.py`: `max_rejected_offers` ve `max_rejected_offers_by_product[].value` en az **2**; 1 verilince `SpecError` (kendim denedim: skaler 1 ve kural değeri 1 reddedildi, 2 kabul). Docstring anlamı açık yazıyor: kural dışı tarih/tutar teklifleri sayılır, düz ret sonrası persuasion sayısı değildir, en az bir karşı öneri hakkı vardır.
- Fixture A ve B: erken bant 2, geç bant 3, skaler 2. raw-a referansı 2/3, changed-a referansı 3/2/3 (brief'in 2/1/2 persuasion sayılarına +1); sentetik fixture alanı taşımıyor, skaler 2. `tests/briefs/` güncellemeleri doğru.
- Davranış (A fixture'ı, erken bant kart, `days_late` 4):
  - son tarihten sonraki ilk tarih (`2026-12-30`) → `date_too_late`, `offer_progress = rejected`, öneri **2026-11-02**; çağrı kapanmıyor, agent karşı öneri turu yapabiliyor. 2026-11-02 el hesabıyla 12. iş günü (26 Ekim tatil atlanarak): doğru.
  - karşı öneri sonrası geçerli tarih (`2026-10-28`) → `ok`, `ready`.
  - ikinci farklı geçersiz teklif → `limit` (çağrı kapanır); aynı geçersiz teklifin tekrarı sayacı artırmıyor (3 kez aynı tarih: sayaç 1'de kaldı).
  - geç bant kredi (`days_late` 20): 1. ve 2. geçersiz teklif `rejected`, 3. → `limit`; öneri 2026-10-23 (7. iş günü, doğru).

## Bulgu 2: kapandı (ürün limiti dolunca diğer ürünlerle devam)
Brief B fixture'ı (kart + kredi), `check_offer` doğrudan çalıştırıldı:

| Senaryo | Sonuç |
|---|---|
| Ürün 1 limiti doldu, ürün 2 henüz işlenmedi | ürün 1 `offers_noted`'a girdi, `offer_progress = more` (negotiate'a döner) |
| Ürün 1 tükendi, sonra ürün 2 kabul | `ready`, kabul edilen yalnız ürün 2 (confirm_record kaydeder) |
| Ürün 1 kabul, sonra ürün 2 tükendi | `ready` (ürün 1 kayda gider, çağrı kapanmıyor) |
| İki ürün de tükendi, hiç kabul yok | ancak son üründe `limit` (closing → `offer_limit`) |
| Tek ürünlü A, limit dolunca | `limit` (closing) |

`check_offer` geçişleri: `ready → confirm_record`, `limit → closing`, `always → negotiate` (rejected/more negotiate'a düşer). Sayaçlar ürün başına; ürün 1'in reddi ürün 2'nin sayacını tüketmiyor (`{"1": 2, "2": 1}`). Testler hem "ilk tükenir, ikinci kabul" hem "ikisi de tükenir, son üründe kapanır" yollarını kapsıyor.

## Not düşülen ürün (Bilgi, sonraki iş)
- Tükenen ürün yalnızca kodda `offers_noted`'a ekleniyor; Brief B kural 8 ("söz verilmeyen ürün için `add_note` çağır, reason `refused` ...") gereği ledger'da not **yazılmıyor**. Yani ürün 1 tükenip ürün 2 kabul edilirse çağrı doğru ilerliyor ama ürün 1'in notu eksik kalır. Bu değişiklikten önce de yoktu (T-005b-fix açık soru 1); Brief B hepsi-ya-hiç vakalarında önem kazanıyor. İlk Brief B chat testinde bu vaka gözlemlensin.
- `more` döndüğünde `offer_message` hâlâ tükenen ürün için "son tarihi öner" cümlesini taşıyor; agent o ürünü bırakıp bırakmayacağını bilmiyor. Chat'te agent ürün 1'de ısrar ederse mesaja "bu ürün için limit doldu, diğer ürünlere geç" cümlesi eklenmeli.

## Hardcode ve kurallar
Builder kodunda brief değeri yok. Freya isteği yok, stdlib, testler çevrimdışı.
