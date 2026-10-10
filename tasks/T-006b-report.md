# T-006b raporu: dağınık ve değiştirilmiş brief'ler (extraction provası)

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

Yalnızca `tests/briefs/` altında test verisi üretildi.

- `builder/` dosyalarına dokunulmadı; oraya hiçbir şey yazılmadı. Builder kodu yalnızca okuma amaçlı kontroller için çalıştırıldı.
- Freya yok, commit yok, `env.sh` yok, canlı model çağrısı yok.
- `python3 -m unittest` yeşil.
- Görevdeki isteğe bağlı referans spec'i `tests/fixtures/spec-changed-a.json` yerine `tests/briefs/changed-a/reference-spec.json` olarak koydum. CTO "sadece `tests/briefs/` altında" dediği için. Aynı biçimde raw-a için de bir referans ekledim.

```
tests/briefs/
  README.md                     çalıştırma, karşılaştırma ve kritik değerler
  raw-a/
    01-email-thread.md          yöneticinin e-posta zinciri (açılış, çağrı değişkenleri, dolandırıcılık sorusu, kapanış)
    02-policy-extract.md        numaralı poliçe maddeleri CP-7 (üçüncü kişi, kimlik, tarihler, tutarlar, kayıt, özel durumlar)
    03-outcome-codes.csv        16 satırlık outcome/reason kod listesi
    04-holidays.txt             beş tatil, beş farklı ISO dışı biçimde
    05-memo.md                  sonraki memo: iki kuralı değiştiriyor
    expected.md                 memo sonrası geçerli kurallar (elle yazıldı)
    reference-spec.json         elle yazılmış referans spec
  changed-a/
    brief-changed-a.md          Brief A yapısında, değerleri değişmiş brief (Kestrel Bank)
    openapi-changed-a.json      aynı araç adları; alan adları, enum'lar ve kuyruklar değişmiş
    expected.md                 doğru çıkarmanın içermesi gereken değerler (elle yazıldı)
    reference-spec.json         elle yazılmış referans spec
```

## raw-a

Brief A'nın 47 kuralı beş dokümana dağıtıldı. Dokümanlarda gürültü de var: e-posta başlıkları, imza, gizlilik notu, "1–3. bölümler çıkarıldı", tatil adları, "2025 listesini yok say", CSV'de `policy_ref` sütunu.

**Memo iki kuralı değiştiriyor:**

1. Erken bandın son tarihi 12. iş gününden **10. iş gününe** iniyor.
2. Kimlik soruları artık **önce telefonun son dört hanesi, sonra doğum tarihi** sırasıyla soruluyor.

İki değer de kit OpenAPI enum'unun içinde kaldığı için raw-a kit OpenAPI ile çalışıyor.

**Tatil biçimleri:** `Mon 26 Oct 2026`, `Thursday 26th November 2026`, `Fri 25/12/2026`, `January 1, 2027` ve diğerleri.

**`expected.md`:** Değişen iki kuralı eski ve yeni değerleriyle bir tabloda veriyor; ikisinin de `overrides` listesinde görünmesi gerektiğini yazıyor. Ayrıca değişmeyen bütün değerlerin listesi ve doğru çıkarmanın yok sayması gereken gürültü listesi var.

**Referans spec:** Güncel fixture A'dan türetildi; memonun iki değişikliği uygulandı. Fixture A'da olmayan şu kısımlar tamamlandı:

- tablo satırları `transferred/restructuring`, `transferred/support`, `no_promise/hardship`; transfer satırlarının hepsinde `wins_over_promise`;
- özel yollar `restructuring`, `hardship` (önce soru, sonra `support` kuyruğu) ve `hardship_declined`;
- `human` yolu doğrulamadan önce de geçerli.

## changed-a

Brief A ile aynı başlıklar ve aynı kural numaraları; değerler farklı. Ayrıntılı tablo `changed-a/expected.md`'de.

**Brief'te değişenler:**

- **Hitap:** ad ve soyadla.
- **Açılış ve kimlik:** belirsizlikte 3 soru hakkı; 3 kimlik sorusu (postcode, birth_year, account_last4); 2 yanlış cevap hakkı.
- **Takvim:**
  - Cumartesi iş günü (`non_business_weekdays = [7]`).
  - Farklı tatiller.
  - En erken söz tarihi yarın.
  - **3 band:** 8., 5. ve 3. iş günü; ikna denemeleri 2, 1 ve 2.
  - "next <gün>" en yakın gün demek (`upcoming`).
- **Tutar tabanı:** Overdraft için bakiyenin %25'i, yani `share` alanını sınıyor.
- **Kayıt ve kapanış:** 3 kayıt denemesi; söz kaydından sonra söylenecek cümle ve vefat cümlesi farklı; 6 outcome ile 14 reason tamamen yeni.

**`openapi-changed-a.json`'da değişenler (araç adları aynı):**

| Araç | Değişen |
|---|---|
| `verify_identity` | soru enum'u; cevap alanları (`answer_ok`, `tries_remaining`, `identity_confirmed`); ipucu `format_postcode` |
| `get_account` | ürün listesi `late_accounts`; ürün alanları `account_ref`, `kind` (card/overdraft/loan), `arrears`, `days_overdue`, `min_due`, `monthly_payment` |
| `create_promise` | ürün alanı `account_ref`, tarih alanı `pay_date` |
| `close_call` | alanlar `result` / `reason_code`; reason artık bir enum |
| `transfer_to_agent` | kuyruklar `hardship_team`, `payment_plans`, `general_enquiries` |
| `add_note` | gerekçe enum'u |
| sunucu | `.invalid` adresi (gerçek bir servis yok) |

## Yaptığım kontroller (offline, builder koduna dokunmadan)

- **`spec.py`:** İki referans spec de doğrulamadan geçiyor; Codex'in yeni offer alanları (`next_weekday`, `max_rejected_offers_by_product`) dahil.
- **Kanıt kontrolleri (T-006 Fix 2):** İki referans spec de extractor'ın kanıt kontrollerinden kendi dokümanlarıyla **sıfır hatayla** geçiyor. Yani doğru bir çıkarma yanlışlıkla onarıma düşmez.
  - raw-a'daki beş farklı biçimli tatilin hepsi tanınıyor.
  - Tablo ve CSV satırlarındaki outcome/reason çiftleri aynı satırda bulunuyor.
  - 10, 7 ve 0 (`today`) gün sayıları yazılı olarak bulunuyor.
- **Madde sayısı:** Kapsama maddeleri raw-a'da 202, changed-a'da 166.
- **Render:** İki durumda da `--spec <referans> --print` başarılı (20 adım, 7 araç).
  - changed-a çıktısında araca giden alanlar spec üzerinden doğru eşleniyor (`account_ref`, `pay_date`, `late_accounts`, `result`/`reason_code`, `identity_confirmed`).
  - Kalan `products` / `product_id` kelimeleri yalnızca kodun iç adları (CONFIG anahtarları ve ara sözlük); araca giden bir alan değil.
  - Renderer değiştirilmiş araç sözleşmesiyle genel çalışıyor.
- **Karşılaştırma aracı:** `compare_spec.py` raw-a referansıyla fixture A arasında beklenen farkları gösteriyor (soru sırası, `offer.latest`, eklenen satırlar ve yollar). changed-a referansı kendisiyle karşılaştırılınca 0 fark çıkıyor.

## Canlı çalıştırma (CTO)

Komutlar `tests/briefs/README.md`'de:

- raw-a: beş doküman sırayla, en sonda OpenAPI.
- changed-a: brief ve değiştirilmiş OpenAPI.
- Her biri için `compare_spec.py` komutu.
- changed-a sonucunda Brief A veya kit değeri kalıp kalmadığını tarayan bir `grep` (çıktı vermemeli).

## Gözlemler ve açık sorular

1. **Tatil kanıtı gevşek.** Tatil kontrolü dokümanlarda yazılı *herhangi* bir tarihi kabul ediyor. raw-a'da e-posta başlıklarındaki tarihler de (`5 Oct 2026` vb.) kanıt sayılıyor; e-posta tarihiyle aynı olan yanlış bir "tatil" bu yüzden geçer. Bağlama bakmak (tatil listesi yakınında olmak) daha sıkı olur ama kırılgan. Canlı raw-a koşusunda `offer.holidays`'e bakın. Sorun çıkarsa `builder/extract.py`'de küçük bir değişiklik (Codex şu an orada çalışmıyor; kararınız).
2. **Yanlış cevap hakkını brief değil araç uyguluyor.** changed-a'da "2 yanlış cevap" yalnızca kural metnine gidebilir. Spec'te bunun için bir alan yok ve gerek de yok: araç `tries_remaining` döndürüyor ve iskelet onu okuyor.
3. **İki kapanış davranışı spec'te birebir yok.** "İki kez konuşmak istemiyorum" ve "doğrulamadan önce reddederse" kurallarının karşılığı yok. Canlı Brief A çıkarması bunları özel yol olarak yazmıştı. Referanslara eklemedim; README bu yollardaki farkların elle değerlendirilmesini söylüyor.
4. **changed-a'da `close_call.reason` artık bir enum.** Extractor'ın kanıt kontrolü bu enum'u ayrıca kontrol etmiyor (çift kontrolü ve outcome enum'u var). Renderer de reason enum'una bakmıyor. Brief tablosundaki bütün reason'lar enum'da olduğu için sorun yok; yine de bir hidden brief'te enum ile tablo çelişirse fark edilmez.
