# F-040 review (extraction: next_weekday, geçersiz teklif sınırı, türetilmiş bitiş durumları)

Rapor: tasks/F-040-report.md; bulgu docs/UAT-FINDINGS.md F-040. Kod düzenlemedim, model veya Freya'ya istek atmadım. `python3 -m unittest`: 159 test geçiyor. Kapsam: `builder/extract.py`, `builder/prompts.py`, `tools/compare_spec.py`'deki F-040 değişiklikleri; build.py/selftest.py (T-007) dahil değil. Canlı yeniden koşuların çıktıları henüz yok (traces/ altındaki spec dosyaları eski koşulardan).

## Karar: düzeltme gerekli
`merge_groups` içinde bir girinti hatası, üç grubun `overrides` listesini siliyor ve sonuncuyu üç kez kopyalıyor (bulgu 1). Testler bunu yakalamıyor; canlı tekrarda raw-a memo geçersiz kılmaları spec'ten kaybolur. Tek satırlık düzeltme, ama bu olmadan canlı koşuların sonuçları yanıltıcı olur. Diğer değişiklikler (next_weekday, geçersiz teklif sınırı, türetilmiş durumlar) amaca uygun; iki küçük zayıflık (bulgu 2, 3) aşağıda.

## Bulgular

### 1. [Yüksek, regresyon] `merge_groups` yeni blok `overrides` döngüsünü bölmüş
- `builder/extract.py` ≈ satır 694–708: `for name, reply in groups.items():` döngüsünün gövdesi yalnızca `provenance.update(...)`. Yeni "derived" blokları (fonksiyon düzeyinde, 4 boşluk) araya girmiş; ardından gelen `if isinstance(reply.get("overrides"), list): overrides.extend(...)` satırı (8 boşluk) artık `for prefix, entries in (...)` döngüsünün içinde kalmış. `reply` o noktada ilk döngüden kalan son grup (outcomes).
- Kanıt (kendim çalıştırdım, kayıtlı Brief A cevaplarıyla; dört grubun her birine ayrı bir override koydum): birleşik sonuç `['N4', 'N4', 'N4']`, yani opening_identity, flow ve offer gruplarının override'ları kayboldu, outcomes grubunun override'ı üç kez tekrarlandı. Canlı raw-a'da memo değişikliklerinin (12→10 iş günü, soru sırası) bulunduğu gruplar opening_identity ve offer; yani `overrides` boş ya da yanlış çıkar. İki sonuç: (a) spec'in denetim izi bozuluyor, (b) T-006'nın "eski metne atıf" hata kuralı (`overrides`'a bakan kontrol) devre dışı kalıyor, memo'yu yok sayan bir çıkarma yakalanmaz.
- Testler neden geçiyor: kayıtlı cevapların `overrides` listeleri boş.
- **Düzeltme:** `if isinstance(reply.get("overrides")...)` satırlarını `for name, reply in groups.items():` döngüsünün gövdesine geri taşıyın (provenance.update ile aynı girinti), yeni derived bloklarını döngüden sonra bırakın. Testi ekleyin: dört grupta birer override, birleşik listede dördü bir kez.

### 2. [Orta-Düşük] "derived:" öneki yalnızca türetilmiş durumlar için değil, her kaynak alanı için alıntı kontrolünü atlıyor
- `_Checker.excerpt` artık `startswith(("fallback", "derived"))` ise hiçbir şey denetlemiyor ve bu her `rule()` kaynağı için geçerli. Denedim: `{"text": "Always offer a 20% discount.", "source": "derived: seems sensible"}` → hata yok, uyarı yok; aynı kural uydurma bir kaynak metniyle uyarı alıyor. Rapor ve istek "alıntı zorunluluğu yalnız türetilmiş durumlar için kalksın" diyor; şu an kural kaynaklarında da delik var (uyarı seviyesinde bir güvenlik ağı, ama kural uydurmaya karşı tek ağ).
- **Düzeltme:** `derived` öneki yalnızca şu yollarda geçsin: `derived_states.*`, route `end` olan açılış/üçüncü kişi/pazarlık girdilerinin `source`'u ve `provenance["outcomes.state.*"]`. Kural kaynaklarında (`*.rules[i].source`, `outcomes[].when/say.source`, `special_paths[].when/say.source`) `derived` gelirse hata ve onarım ("bir kural kaynağı brief'ten alıntı olmalı"). `fallback` yalnızca `sources` haritasındaki veri alanları için kalsın.

### 3. [Düşük] `next_weekday` kanıtı yönü doğrulamıyor
- `_NEXT_WEEKDAY = \bnext\W{0,3}(monday..|weekday|<weekday>)`: dokümanda "next Friday" geçmesi yeterli; `following_week` mı `upcoming` mı olduğuna bakmıyor. Brief A'daki "following calendar week" yerine model `upcoming` yazsa (veya changed-a'da tersini) kontrol geçer. Ayrıca "next Friday" bir örnek cümlede (tanım olmadan) geçerse kontrol onu da kabul eder.
- **Düzeltme (küçük):** `following_week` için aynı cümlede `following`/`next calendar week`/`week after` benzeri, `upcoming` için `nearest`/`first`/`upcoming`/`next such` benzeri bir sözcük arayın; bulunmazsa hata ve onarım ("yön dokümanla uyuşmuyor"). `ask` hep geçerli kalsın. Canlı koşuda A ve raw-a için `following_week`, changed-a için `upcoming` beklenir; çıkarsa kod bunu doğrulamasa da compare_spec yakalar.

## Doğrulananlar

**`next_weekday` çıkarma kuralı:** `EXTRACT_OFFER_TASK` üç değeri tanımlıyor ve "dokümanlar tanımlamıyorsa `ask`" diyor; kaynak `sources["offer.next_weekday"]`'e yazılıyor; alan yoksa `spec.py` `ask` varsayıyor. Kod kontrolü "next <weekday>" metni yoksa `following_week`/`upcoming`'i reddediyor (testli). Yönü doğrulamadığı için bulgu 3.

**`max_rejected_offers` anlamı:** prompt alanı doğru tanımlıyor: geçersiz (tarih/tutar kontrolünden geçemeyen) farklı teklif sayısı, en az 2; "NOT the number of persuasion attempts: never copy a persuasion or attempt count"; brief sınır koymuyorsa 2 ve kaynak `fallback: no invalid-offer limit in the documents`; by_product yalnızca dokümanlar ürün grubuna göre farklı geçersiz-teklif sınırı koyuyorsa, aksi `[]`, "persuasion attempts per band are not invalid-offer limits" cümlesi var. Kod: kaynak `persuasion|attempt` içeriyorsa (ve fallback/derived değilse) iki alan için hata ve onarım; `spec.py` 2 altını reddediyor ve hata offer grubuna yönlendiriliyor (testli). Persuasion sayısı artık kopyalanamaz; T-005g review bulgu 1'in kökü kapanmış. T-006b referansları `2` ve `[]` (persuasion+1 yerine); önceki önerim buydu ("geçersiz teklif sınırı koymuyor"), doğru. Fixture A/B hâlâ 2/3 (Codex'in dosyası): extractor `[]` üretince `offer.max_rejected_offers_by_product` satırında beklenen DIFF çıkacak. Brief A bir geçersiz-teklif sınırı vermediği için fixture'ın `[]` olması tutarlı olur; CTO/Codex kararı.

**Çerçeve bitiş durumları:** `DERIVED_REQUIRED_STATES = account_failed, offer_limit, hangup, hangup_unverified` her spec'te bir satıra eşlenmek zorunda; eşlenmezse onarım mesajı "en yakın satıra eşle ve `derived_states`'e yaz" diyor. `derived_states` her durumun gerçekten bir satıra eşlendiğini ve nedenin boş olmadığını kontrol ediyor; merge bunları `provenance["outcomes.state.<durum>"] = "derived: <neden>"` yazıyor (satır 696–698, bu kısım doğru çalışıyor). Açılışta route `end` olan bir ret değeri zorunlu (testli). `compare_spec`: açıkça `default`'a eşlemek ile hiç eşlememek aynı sayılıyor, başka satıra eşleme fark olarak çıkıyor (mantıklı, çalışma anı davranışıyla uyumlu). Alıntı kontrolünün atlanması kapsamı için bulgu 2.

**Araç gerektiren durumların pazarlık niyeti sayılması:** prompt (`EXTRACT_FLOW_TASK`) "route end yalnızca ödemeyi/konuşmayı reddetmek için; ödendi, itiraz, transfer, zorluk özel yollardır" diyor; gruplar arası kod, aracı olan bir özel yolun outcome/reason çiftiyle kapanan pazarlık değerini reddediyor. Araçsız durumlar (ödendi, itiraz) yalnızca prompt ile korunuyor; ret satırı meşru araçsız yollarla paylaşılabildiği için bu mantıklı bir sınır. Canlı koşularda gözlenen asıl sorunu (transfer/ödendi'nin pazarlık niyeti olması) doğru hedefliyor.

**Prompt'larda brief değeri:** yeni/değişen metinlerde (EXTRACT_OPENING_IDENTITY_TASK, EXTRACT_FLOW_TASK, EXTRACT_OFFER_TASK, EXTRACT_OUTCOMES_TASK, CLOSE_STATE_GUIDE, PROMPTS.md) banka adı, ürün tipleri, outcome/reason kodları, sayılar, saat, tarih ya da kuyruk adı yok; yalnızca alan adları, çerçeve durum adları ve genel koleksiyon kategorileri ("ödeme zaten yapıldı", "borç reddi", "transfer", "mali zorluk") var. "2 (one invalid offer, then the agent's counter-offer may be rejected once)" çerçeve gerekçesi, brief değeri değil. Sızıntı testi yeşil.

## Kurallara uyum
Model/Freya çağrısı yok, stdlib, testler çevrimdışı. Anahtar yönetimi değişmedi.

## Düzeltme sonrası bakılacaklar
1. Bulgu 1 düzelince dört canlı koşuyu tekrarla ve `overrides` sayılarına bak: raw-a'da 2 (memo), Brief A'da 0, A+B'de B'nin atıf/üstüne yazma girdileri.
2. Canlıda `offer.next_weekday`, `max_rejected_offers = 2`, `by_product = []`, `derived: …` ile başlayan `outcomes.state.{account_failed, offer_limit, hangup, hangup_unverified}` provenance girdileri, açılış ret değeri ve pazarlık niyetlerinde transfer/ödendi/itiraz değerinin olmaması kontrol edilsin (raporun beklenti tablosu doğru).
3. `derived` sızıntısı (bulgu 2) düzelmeden hidden brief'te uydurma kural kaynağı uyarı vermez.

---

# Fix kontrolü (bulgu 1–3, F-041, fixture A/B; rapor: tasks/F-040-report.md "Fix")

Kod değiştirmedim, model veya Freya'ya istek atmadım. `python3 -m unittest`: 166 test geçiyor. build.py/selftest.py/freya.py (T-007) dahil değil.

## Karar: merge edilebilir
Üç bulgu da kapandı, F-041 değişiklikleri prompt'a brief değeri sokmuyor, fixture A/B değişikliği testlerle tutarlı. Bir bilgi notu (kullanılmayan eski snapshot) var.

## Bulgu 1 (`overrides` döngüsü): kapandı
Aynı denemeyi tekrarladım (kayıtlı Brief A cevapları, dört gruba birer override): birleşik liste artık `['N1', 'N2', 'N3', 'N4']`, her biri bir kez. Rapor, canlı raw-a spec'indeki 6 override'ın outcomes grubunun 2 override'ının üç kopyası olduğunu da doğruluyor (benim bulgumla tutarlı). Test eklenmiş.

## Bulgu 2 (`derived` kapsamı): kapandı
`excerpt()` `derived` önekini yalnızca `derived_ok` verilen yerlerde (route `end` olan açılış/üçüncü kişi/pazarlık değerlerinin `source`'u) kabul ediyor; `derived_states` zaten alıntı istemiyor. Denedim:
- kural kaynağı `derived: seems sensible` → **hata** ("kural kaynağı dokümandan alıntı olmalı");
- kural kaynağı `fallback: none` → hata (fallback yalnızca `sources` haritasındaki veri alanlarında kaldı);
- uydurma alıntı → önceki gibi uyarı.
Önceki delik (uydurma kural + `derived:` = sessiz) kapandı.

## Bulgu 3 (`next_weekday` yönü): kapandı
Kendim denedim:

| Brief | following_week | upcoming | ask |
|---|---|---|---|
| Brief A ("following calendar week") | ok | **hata** | ok |
| changed-a ("nearest such weekday") | **hata** | ok | ok |
| Yalnızca örnek cümle ("may say next Friday") | **hata** | **hata** | ok |

Yön sözcüğü aranıyor; tanımsız örnek cümle artık yeterli sayılmıyor.

## F-041 (ilk tur hata azaltma): prompt'a brief değeri girmiyor, mantık makul
- **Neden analizi:** boş `ask` nesnesi (metin ve kaynak boş) yol başına iki hata üretiyor; Brief A'da 9 yol × 2 = tam 18 hata; onarım mesajı yalnızca "boş olmamalı" dediği için model alanı talimatla doldurmuş ("Take no promise."). Bu, iskelet `ask`'ı müşteriye soru olarak söyleyip yanıt beklediği için gerçek bir davranış hatası. Çıkarım ikna edici ve sayıyla (18) örtüşüyor.
- **Düzeltme:** boş `ask` merge'de düşürülüyor (hata değil); dolu `ask` "?" ile biten tek soru olmalı ve yalnızca `then: close` ile; aksi onarım. `EXTRACT_OUTCOMES_TASK` şimdi `ask`'ın ne zaman konmayacağını söylüyor ve kodun bu grupta uyguladığı altı kontrolü listeliyor (kural kaynakları alıntı; çift tek satırda; özel yol çiftleri tabloda; `tool_args` enum'da; her durum tek satırda; `ask` soru). Trace'e her turun hataları `extract_issue: round=N [grup] yol: mesaj` olarak yazılıyor (60 satır sınırı).
- **Brief değeri taraması:** extraction prompt'larının tamamını (EXTRACT_*, COVERAGE_*, CLOSE_STATE_GUIDE) üç brief ve raw-a dosyalarından çıkardığım jetonlarla taradım: ortak snake_case değer yok; banka adları, kodlar, sayı/saat/tarih, kuyruk/alan adları yok. Geriye kalan tek eşleşmeler genel sözcükler: `callback_scheduled` / `callback_failed` çerçeve durum adları ("callback" sözcüğü), "titles" (alıntı dışı madde tanımında) ve "queue" ("Never invent ... queue" cümlesinde). Hepsi önceki incelemelerde kabul ettiğim çerçeve/genel dil; brief'e özgü değer değil.
- Küçük not: "ask `?` ile bitmeli" kuralı, `?` olmayan meşru bir soruyu da onarıma gönderebilir (örn. "Shall I connect you now."); onarım mesajı nedeni söylüyor, kabul.

## Fixture A/B `max_rejected_offers_by_product = []` ve testler: tutarlı
- Fixture A/B ve kayıtlı Brief A cevapları, T-006b referansları (`raw-a`, `changed-a`) hepsi `[]`, skaler 2; spec ve extraction tarafı artık aynı şeyi söylüyor, canlı karşılaştırmadaki beklenen DIFF kalktı.
- Kendim çalıştırdım (A ve B fixture'ı, bugün 2026-10-14, kart `days_late` 4 ve kredi `days_late` 20): her iki bantta 1. geçersiz teklif `rejected` (karşı öneri turu), 2. `limit`; yani erken ve geç bant aynı davranıyor (önceden geç bant 3'tü). Brief A geçersiz-teklif sınırı vermediği için tek skaler 2 doğru.
- `test_rejection_limit_is_selected_by_product_band` artık bant kurallarını kendi veriyor (`run_offer(..., offer=...)`, sentetik, yorumda belirtilmiş); bant mekanizması hâlâ test ediliyor. Yeni test fixture'ın skaler 2'yi kullandığını doğruluyor. İkisi tutarlı.
- **Bilgi:** `tests/fixtures/extract/brief-a-reference.json` hâlâ eski 2/3 `max_rejected_offers_by_product` taşıyor, ama hiçbir test ya da araç bu dosyayı okumuyor (aradım). Karışıklık yaratmaması için ya silin ya da `[]` yapın.

## Kurallara uyum
Model/Freya çağrısı yok, stdlib, testler çevrimdışı.

## Canlı tekrar için
Raporun beklenti tablosu doğru. Ek olarak: raw-a `overrides` sayısı 2; ilk tur hata sayıları (`extract_issue` satırları) Brief A için eskiden 18 idi, boş `ask` düzeltmesiyle belirgin düşmeli; `ask` alanları yalnızca gerçek sorular ("önce yardımcı olabilir miyim?", "destek ekibine bağlayayım mı?").
