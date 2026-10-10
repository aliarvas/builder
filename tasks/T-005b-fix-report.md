# T-005b-fix raporu: review bulguları 1–6

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10 · **Kaynak:** `reviews/T-005b-review.md` "Bulgular"

## Özet

Bulgu 1–6 düzeltildi; bulgu 7'ye (T-006 notu) dokunulmadı. `python3 -m unittest` 81 testin hepsini geçiyor (öncesi 75). `--print --spec` fixture A ve B ile çalışıyor. Freya'ya istek yok, commit yok, `env.sh` okunmadı.

Değişen dosyalar: `builder/workflow.py`, `builder/offer_check.py`, `builder/build.py`, `tests/test_multi_step.py`. Prompt metni değişmedi (`docs/PROMPTS.md` yeniden üretildi, fark yok). Spec formatı ve fixture'lar değişmedi.

Adım sayısı:

- A: değişmedi (34 normal + 3 global).
- B: 32 + 2'den 34 + 3'e çıktı. `product_dispute` artık iki küçük global giriş adımı, bir konuşma adımı ve bir `_done` adımı (bulgu 3).

En büyük prompt identity: A'da yaklaşık 506, B'de 479 token.

## Bulgu başına değişiklik

### 1. Çok ürünlü akışta erken `ready`

- `check_offer` artık extractor'ın verdiği ürün sayısına bakmıyor. `ready` ancak `get_account`'un döndürdüğü **her ürün** ya kabul edilmiş bir teklife ya da kaydedilmiş bir nota sahip olunca geliyor.
- Not düşülen ürünler yeni `offers_noted` listesinde tutuluyor; `offer_setup` bunu boş başlatıyor.
- Ürün bazlı özel yol (B'de itiraz notu) başarılı olunca `special_<id>_done` kod adımı ürün numarasını listeye ekliyor. Numara `add_note_args.<numara alanı>`'ndan okunuyor.
- `_done` adımı, bütün ürünler kapsanmışsa ve en az bir kabul varsa doğrudan `confirm_record`'a gidiyor.
- Müşteri "bu kadar" derse mevcut kabullerle `confirm_record`'a giden geçiş aynen duruyor.
- `expected_count` çıkarımı artık hazır olma kararında kullanılmıyor. Spec alanı ve `confirmation_progress`'teki yedek kullanımı yerinde bırakıldı.
- **Test:** extractor "1" dese de iki üründe bir kabulle `more`; ikinci ürün not düşülmüşse `ready`; başarısız not sayılmıyor; bozuk girdide hata yok.

### 2. Kimlik aracının soru alanı adı kodda sabitti (`field`)

- `_check_identity_fields` artık alanı adıyla aramıyor. Kimlik aracının gövdesinde, spec'teki bütün soru alanlarını kapsayan bir enum'u olan özelliği arıyor.
- Bulamazsa build durmuyor: trace'e `warning: ... not validated` yazılıyor. `build_spec_workflow` isteğe bağlı bir `warnings` listesi alıyor; `build.py` bunları trace'e yazıyor.
- **Test:** OpenAPI'de alan `question` olarak yeniden adlandırılınca build uyarısız çalışıyor; enum uyuşmazsa tek bir uyarı yazılıyor ve build devam ediyor.

### 3. Eski `special_result_<id>`, yol ikinci kez tetiklenince araçsız çıkış

Modelin doldurduğu araçlı yollarda (B `add_note`) yapı değişti:

- **Global giriş adımları:** her kaynak adım için bir küçük global **kod** adımı var (`special_<id>_at_<adım>`), yalnızca o adımda tetikleniyor. Eski sonucu boşaltıyor ve dönülecek adımı `special_result_<id>_from`'a yazıyor.
- **Konuşma adımı:** `special_<id>` normal bir konuşma adımı. Aracı model çağırıyor; çıkış yalnızca o çağrının sonucuna bağlı.
- **Dönüş:** `special_<id>_done`. Ürünü not listesine ekliyor, sonra kaydedilen kaynak adıma **açık hedefle** dönüyor. Bu yolda artık `__previous__` yok.
- **Birleşen geçişler:** engine aynı hedefli geçişleri birleştiriyor (biri koşulsuzsa hepsi koşulsuz olur). Bu yüzden son kaynak adım yalnızca `always` yedeğiyle hedefleniyor.
- **Değişmeyenler:** araçsız ve engine'in çalıştırdığı yollar zaten her girişte taze çalışıyor. `ask`'lı yollar yalnızca kapanışa gidiyor, bir kez tetikleniyor.
- **Test:** giriş kodu eski `True`'yu siliyor ve kaynağı yazıyor; `_done` geçiş sırası; bu yolda `__previous__` yok.

### 4. Binlik ayırıcılı tutar metni

`parse_amount` artık şöyle davranıyor:

- Hem nokta hem virgül varsa sonuncusu ondalık.
- Yalnızca virgül varsa ve son virgülden sonra 3 hane (veya birden çok virgül) varsa binlik; aksi halde ondalık.
- Birden çok nokta varsa binlik.
- **Test:** `1,200` → 1200, `1.200,50` → 1200.5, `1,200.50` → 1200.5, `12,50` → 12.5, `1.200.000` → 1200000, `$1,500` → 1500.

### 5. Bugün iş günü değilken `date_too_early` etiketi

- Teklif, sayılan en erken tarihte veya sonrasındaysa ve yalnızca iş günü olmadığı için ileri kaydırıldıysa (örn. bugün tatil) sonuç artık `date_not_business_day`. Gerçekten erkense yine `date_too_early`.
- **Test:** Brief A tatili 2026-10-26'da bugüne teklif → `date_not_business_day`, öneri 10-27; dünkü tarih → `date_too_early`.

### 6. Sızıntı testinde OpenAPI alan adlarının toptan izni

- OpenAPI alan adlarının toptan izni kaldırıldı; yalnızca OpenAPI **değerleri** izinli.
- Genel sözcükler dar, dosya bazlı bir listede ve her birinin gerekçesi yazılı: `type`, `default`, `close`, `return`, `failed`. Bir sözcük o dosyalar dışında geçerse test kırılıyor.
- İskelet sözlüğü (`CLOSE_STATE_NAMES`, `OFFER_UNITS`, `OFFER_ADJUST`) hâlâ spec.py'den türetiliyor.
- Ek kontrol: `field` literal'i `workflow.py`'de geçmemeli (bulgu 2'nin geri gelmemesi için). Spec formatının kendi `field` anahtarı spec.py/offer_check.py'de izinli; o bir tool alan adı değil.

## TO-CONFIRM (chat testi)

1. **Global kod adımları:** global node `code` tipinde olabiliyor mu, passthrough olarak `special_<id>`'a geçiyor mu? `api_request` tipindeki global için aynı soru T-005b'den açık.
2. **Hook değişkeni:** `add_note_args.<numara alanı>` kod adımında `vars` içinde düz anahtar olarak görünüyor mu? `_done` kodu iç içe `add_note_args` sözlüğünü de deniyor. Rereview notu 3 ile aynı soru.
3. **Brief B, iki ürün:** biri itiraz, biri teklif. Gözlenecekler: not iki kez yazılabiliyor mu, bütün ürünler kapsanınca `confirm_record`'a gidiliyor mu, ledger'da tek söz ve tek not var mı?

## Açık sorular

1. Ret, zorluk veya ödendi notları (Brief B kural 8) için hâlâ ayrı bir yol yok; yalnızca spec'teki özel yollar not düşebiliyor. Bütün ürünler not düşülüp hiç kabul yoksa negotiate kapanışı müşteri niyetine bağlı. Ürün bazlı kapanış nedeni (Brief B "Closing") T-005 kapsamında.
2. `expected_count` çıkarımı artık yalnızca `confirmation_progress`'te yedek. İstenirse kaldırılabilir.

## Fix 2 (review "Fix kontrolü": Yeni-1, Yeni-2)

**Sonuç:** `python3 -m unittest` 85 testin hepsini geçiyor (öncesi 81). Freya yok, commit yok, `env.sh` okunmadı. Değişen dosyalar: `builder/workflow.py`, `tests/test_multi_step.py`.

### Yeni-1: Aynı hedefli geçişlerin birleşmesi

**Kök neden:**

- `_done` adımında `ready → confirm_record` ve `always → confirm_record` aynı hedefe gidiyordu. Freya bunları birleştirince geçiş koşulsuz oluyor.
- Taramada aynı hedefi iki kez yazan üç düğüm daha çıktı: `negotiate` (iki `confirm_record` geçişi), `close_record` (iki `end_call` geçişi) ve B `special_product_dispute` (başarı ve başarısızlık aynı `_done` adımına). Üçü de yalnızca deterministik koşullar taşıdığı için birleşince doğru OR veriyordu, ama sıra engine'e kalıyordu.

**Düzeltme:**

1. **Genel gruplama:** `group_transitions_by_target`. Üretimin sonunda her düğümün (global node'lar dahil) geçişleri hedefe göre gruplanıyor.
   - Aynı hedefe giden deterministik geçişler, ilk geçtiği yerde tek bir OR geçişine dönüşüyor; açıklamalar birleşiyor.
   - Bir grupta koşulsuz (`always`) ya da niyet/araç geçişi başka bir geçişle karışırsa build `internal:` hatasıyla duruyor. Bu bir builder hatasıdır, sessizce birleştirilmez.
2. **`_done` üreticisi (`_done_transitions`):** hiçbir hedef iki kez çıkmıyor.
   - **Kaynaklar arasında `confirm_record` varsa** (B): `from == negotiate AND offer_progress != ready → negotiate`, sonra `always → confirm_record`. Ayrı bir `ready` geçişi yok; ready durumu zaten yedeğe düşüyor.
   - **Yoksa:** `ready → confirm_record`, son kaynak hariç her kaynak için `from == kaynak → kaynak`, en sonda `always → son kaynak`.
3. **Sonuçlar:**
   - B `_done`: `negotiate`, sonra `confirm_record`.
   - `close_record`: `end_call` (başarı **veya** 2 deneme), sonra `close_attempt`.
   - `negotiate`: `confirm_record`'a tek bir geçiş.

**Testler:**

- Bütün fixture'larda, her düğümde ve her global node'da hiçbir `target_node` iki kez yazılmıyor.
- Gruplama koşulları birleştiriyor; koşulsuz geçiş karışınca hata veriyor.
- `confirm_record` kaynağı olmayan bir yolda `ready` kısayolu korunuyor.
- B `_done` adımının `negotiate` geçişi `offer_progress != ready` koşulunu taşıyor.

### Yeni-2: Araç adları kodda sabit

- OpenAPI'de builder'ın beklediği bir banka aracı yoksa build artık açık bir mesajla duruyor: hangi araçların eksik olduğu, dosyada hangilerinin bulunduğu ve araç adının OpenAPI yolunun son parçasından alındığı. CLI çıkış kodu 2.
- Örnek: `error: the tool file does not define the bank tools this builder needs: close_call. Tools found: add_note, close_up, … Each tool name is taken from the last part of its OpenAPI path.`
- Araç adları bilinçli olarak sabit kaldı (kitin sabit banka API'si). Yalnızca hata anlaşılır hale geldi.
- **Test:** `/close_call` yolu `/close_up` olarak yeniden adlandırılınca hata mesajı eksik ve bulunan adları içeriyor.
