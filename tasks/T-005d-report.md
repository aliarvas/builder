# T-005d raporu: sadeleşen kapanış yönlendirmesi, güvenli açılış

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

- **Testler:** `python3 -m unittest` 98 testin hepsini geçiyor (öncesi 94).
  - Sızıntı taraması yeşil.
  - Hiçbir adımda `target_node` iki kez yazılmıyor.
  - Prompt bütçesi her adımda 1.500'ün altında: en büyük A'da ~558, B'de ~524 token.
- **Doküman:** `docs/PROMPTS.md` yeniden üretildi.
- **Kurallar:** Freya'ya istek yok, commit yok, `env.sh` okunmadı, `builder/` içine brief değeri girmedi.

Değişen dosyalar:

- **Kod:** `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`.
- **Test:** `tests/test_multi_step.py`.
- **Doküman:** `docs/PROMPTS.md`, `docs/UAT-FINDINGS.md` (F-024).

## 1. Etiket adımları olmadan kapanış

### Adım sayısı

| Fixture | Normal adım (önce → sonra) | Global | `close_<state>` etiket adımı |
|---|---|---|---|
| A | 34 → 19 | 3 | 18 → 2 |
| B | 34 → 21 | 3 | 16 → 2 |
| Sentetik | 29 → 18 | 1 | 14 → 2 |

Sonraki adım sayılarına yeni `opening_reask` adımı dahil (bölüm 2).

### Nasıl çalışıyor

- **Doğrudan geçiş:** kaynak adımlar doğrudan `closing`'e gidiyor. Deterministik koşullar aynı kaldı.
  - Aynı adımdan `closing`'e giden birden çok geçiş tek bir OR geçişinde birleşiyor (`group_transitions_by_target`).
  - Örnekler: `third_party` adımındaki geri arama ve kapanış değerleri, `confirmation_progress`'teki `complete` ve `exhausted` durumları.
- **Tek öncelik tablosu:** `workflow.py` içindeki `close_rules(spec)`. Her satır bir durum ve onun koşulu.
  - Aynı koşul hem kaynak adımın `closing`'e giden geçişi oluyor, hem de `closing`'te yeniden değerlendiriliyor.
  - Böylece yönlendirme ile türetme ayrışamaz.
- **Ortak türetme kodu:** `derive_close_state()`.
  - `closing` ve hang-up aracının pre-hook'u aynı kodu kullanıyor; iki yol aynı satırı seçiyor.
  - Kod koşulları router gibi değerlendiriyor. Hata atmıyor ve `{{`/`}}` içermiyor.

### Öncelik sırası

İlk tutan kural durumu belirler. Sonraki çağrı aşamaları önce gelir; böylece önceki bir aşamadan kalan değişken hiçbir zaman kazanmaz.

0. **Yazılmış `close_state`:** bir kod adımının yazdığı durum her kuralı yener.
   - `opening_unclear`: `opening_unclear` adımı, sınır dolunca yazar.
   - `offer_limit`: `check_offer` adımı yazar.
   - `promise_recorded` / `promise_failed`: `confirmation_progress` adımı yazar.
   - `special:<id>`: araçsız kapanış yolu yazar. Bu yol artık tts'li bir global kod adımı.
   - Etiketli iki durum (aşağıda).
1. `special:<id>`: araçlı kapanış yolunda `special_result_<id>` true.
2. `negotiation:<değer>`: niyet = değer **ve** kabul edilen teklif sayısı < 1.
3. `account_failed`: `account_failure_count` > 0.
4. `identity_failed`: kalan deneme < 1 **ve** kimlik doğrulanmamış.
   - Geçişe "doğrulanmamış" koşulu eklendi. Davranış aynı, çünkü doğrulanma geçişi zaten önce geliyor.
   - Ama artık "doğrulandı + kalan deneme 0" artığı sonraki bir kapanışta `identity_failed` diye okunamıyor.
5. `callback_scheduled`.
6. `callback_failed`.
7. `third_party:<değer>`.
8. `opening:<değer>`.

Hiçbir kural tutmazsa `default` satırı kullanılıyor. Kayıtlı söz kuralı (`wins_over_promise`) değişmedi.

### Korunan iki etiket adımı ve nedeni

- **`close_turn_limit`:** engine'in `max_turn_transition`'ı hiçbir değişken yazmıyor. `<node>.current_turns` şablon değişkeni var, ama code `vars` içinde görünüp görünmediği doğrulanmadı.
- **`close_special_tool_failed`:** engine'in çalıştırdığı özel yol aracında `always` yedeği (HTTP hatası veya `ok` alanı yok) her hata türünde güvenilir bir değişken bırakmıyor. Global node'lar için `<node>_failure_count`/`_success_count` adlandırması doğrulanmadı.

İkisi de yalnızca kendi durumunu yazıyor ve `TAGGED_CLOSE_STATES` dışında etiket adımı üretilemiyor; üretilmeye çalışılırsa `internal:` hatası.

### Eşdeğerlik kanıtı (testler)

- **Yönlendirme simülasyonu:** `test_every_call_end_path_derives_its_state_and_outcome`, testte bağımsız yazılmış küçük bir yönlendirme yürütücüsü kullanıyor.
  - Kod adımlarını çalıştırıyor, ilk tutan geçişi izliyor. Her fixture'da, spec'ten üretilen her çağrı sonu yolunu başlangıç adımından `closing`'e kadar yürütüyor.
  - Kapsadığı yollar: açılış, `opening_unclear` (iki adımdan da), geri arama başarılı/başarısız, üçüncü kişi, kimlik, hesap, `offer_limit` (`check_offer`'a gerçek ret teklifleri gönderilerek), müzakere, söz kaydedildi/başarısız, özel yol başarılı/başarısız, tur sınırı.
- **Beklenti değişmedi:**
  - Çözülen durum, outcome ve reason eski tabloyla aynı.
  - Hang-up pre-hook'u da aynı değişkenlerden aynı outcome'u seçiyor.
  - Kapsanan durum kümesi eskisiyle birebir aynı.
- **Artık değişkenler:** doğrulanmış aşamadaki senaryolar bilerek önceki aşamaların artıklarını taşıyor ("kim açtı" ve kalan deneme 0).
- **Mutasyon kontrolü:** `identity_failed` kuralını korumasız bırakıp en başa taşıyınca 10 test kırıldı; tablo eski haline getirildi.
- Mevcut "kayıtlı söz kazanır" ve Brief A outcome testleri değiştirilmeden geçiyor.

## 2. Açılış

### Selamlaşma, deneme sayılmıyor

- **Yeni değer:** builder, "kim açtı" extraction'ına çerçeve değeri `greeting`'i ekliyor (`spec.OPENING_GREETING_VALUE`). Açıklama genel: yalnızca selam veya hat kontrolü, örneğin "Hello?" ya da "Who is this?".
- **Yönlendirme yok:** bu değer hiçbir geçişi tetiklemiyor. Adım yerinde kalıyor, model soruyu tekrar soruyor (prompt'ta kural var) ve sayaç artmıyor.
- **Ayrılmış değer:** spec kendi seçeneklerinde `greeting` kullanırsa yükleme açık bir hatayla duruyor.

### Tanıtım tekrarlanmıyor

Seçilen mekanizma: ayrı bir yeniden sorma adımı ve `opening` üzerinde `on_enter_first_entry_only: true`.

- **`opening_unclear` artık `opening`'e dönmüyor.** Yeni `opening_reask` konuşma adımına gidiyor. Bu adımın:
  - transitions ve extraction alanları `opening` ile aynı;
  - task'ı tanıtımı içermiyor ("tanıtımı zaten yaptın, sorulmadıkça tekrarlama; soruyu kısaca tekrar sor").
- **Sessizlik yok:** `opening_reask` varsayılan llm girişiyle konuşuyor. Her girişte yalnızca soruyu soruyor.
- **`opening`:** `on_enter_first_entry_only: true` taşıyor. Artık hiçbir adım `opening`'e geri dönmüyor (testte doğrulanıyor), bu yüzden bayrak yalnızca bir güvence.
- **Neden yalnızca bayrak değil:** bayrak tek başına kullanılsaydı yeniden girişte giriş davranışı atlanır ve ajan susardı. T-004 review N7 de bu yüzden uyarmıştı. Girişe özel `prompt` anahtarı da her girişte çalışıyor; ilk girişi sonrakilerden ayırmıyor.

### Önce tanıtım

- **Kural:** sistem prompt'una tek bir genel kural eklendi: "Bu çağrıda bu tanıtımı henüz yapmadıysan, müşteri ne derse desin bir sonraki mesajında önce onu yap: {introduction}".
- **Kapsam:** metin spec'teki `agent.introduction`'dan geliyor ve her adımda geçerli.
- **Maliyet:** her adımın prompt'una yaklaşık 40–90 token ekledi.

## TO-CONFIRM (onaylı chat testi)

1. **Araçsız kapanış yolu (A `already_paid`, `dispute`):** artık tts'li bir global **kod** adımı (önce passthrough konuşma adımıydı).
   - Cümle söyleniyor mu, ardından `closing`'e geçiliyor mu?
   - Tts'li kod adımı `closing_say`'de doğrulandı; global kod adımı ise T-005b'den beri açık.
2. **Code içindeki engine değişkenleri:** `closing` kodunda `vars` içinde şunlar görünüyor mu?
   - `account_failure_count`, `schedule_callback_failure_count`, `schedule_callback_response.data.ok`;
   - `special_result_<id>`, `identity_attempts_left`.
   - Geçişler bunları okuyor; code'un da görmesi gerekiyor. Kit, code düğümü sayaçlarının değişken tablosunda göründüğünü yazıyor.
   - **Görünmezse etkisi:** yalnızca `account_failed` ve `callback_failed` (sayaç yolu) `default` satırına düşer. Çağrı yine kapanır, ama outcome yanlış olabilir.
3. **`on_enter_first_entry_only`:** başlangıç adımında ilk giriş yine konuşuyor mu? Kit örneği başlangıç adımında aynı bayrağı kullanıyor.
4. **Belirsiz cevap sonrası:** `opening_reask` girişinde ajan yalnızca soruyu soruyor mu? Tanıtım tekrar edilmemeli ve sessizlik olmamalı.
5. **Selamlaşma:** "Hello?" `greeting` olarak çıkarılıyor mu? Ajan soruyu tekrar soruyor mu ve `opening_unclear_count` artmadan kalıyor mu?
6. **Önce tanıtım:**
   - Müşteri ilk konuşursa (ör. "Who is this?") ajan önce tanıtımı yapıyor mu?
   - Kural sonraki adımlarda tanıtımın tekrarına yol açmıyor mu?
7. **T-005c hang-up maddeleri (değişmedi):** normal kapanışta ledger'da tek `close_call` ve `hangup_close = skipped`; müşteri kapatınca hesaplanan outcome ledger'a düşüyor mu?

## Açık sorular

1. **Tanıtım kuralının riski:** sistem prompt'undaki kural, model geçmişi kısaltılmış görürse tanıtımı geç bir adımda tekrar ettirebilir (varsayılan `keep_all`, bu yüzden düşük risk). Chat testinde tekrar görülürse kural yalnızca `opening`/`opening_reask`/`third_party` adımlarının task'ına taşınabilir.
2. **Etiket sayısı:** chat testi `<node>_failure_count`'un global api_request adımlarında da yazıldığını gösterirse `close_special_tool_failed` da kaldırılabilir. Tur sınırı için de aynısı `<node>.current_turns` ile mümkün.

## Fix (review T-005d: `opening_reask` kaynağı, `identity_failed` kuralı)

- **(1) `opening_reask` kaynak sayılıyor.**
  - `workflow.py`'de tek bir eşleme var: `STEP_ALIASES = {"opening": ("opening", "opening_reask")}`. Bunu kullanan `source_steps(path)` fonksiyonu, `available_in`'i üretilen adımlara genişletiyor.
  - Üç kullanım yeri de bu fonksiyondan besleniyor:
    - global node'un kaynak listesi, dolayısıyla `excluded_nodes`;
    - modelin doldurduğu araçlı yolların kaynak başına giriş adımları (`special_<id>_at_opening_reask`);
    - `_done` adımının dönüş hedefleri.
- **(2) `identity_failed` kuralı sağlamlaştırıldı.**
  - Kural artık "kalan deneme < 1 **ve** `identity_verified` false/False": iki AND grubunun OR'u, yani mevcut koşul biçimi.
  - Önceki "true'ya eşit değil" biçimi yalnızca `identity_verified` hiç yazılmamışken farklıydı. İki değer aynı `verify_identity` yanıtından eşlendiği için pratikte sonuç aynı.
  - Review'daki karşılaştırma ve mevcut senaryo testleri bunu doğruluyor: bütün çağrı sonu yolları değişmeden geçiyor.
- **Testler:** 100'ün hepsi geçiyor (öncesi 98).
  - `opening` eklenen üç özel yol türü (ask'lı engine aracı, araçsız, modelin doldurduğu araçlı dönüş yolu) `opening_reask`'ta da tetikleniyor. `_done` adımı `opening_reask`'a dönebiliyor. `opening` yoksa iki açılış adımı da kaynak değil.
  - `identity_failed` false/False ile tetikleniyor; değer boşken ya da true iken tetiklenmiyor. Bu hem geçişte hem türetmede kontrol ediliyor.
- Prompt metni değişmedi. Freya'ya istek yok, commit yok, `env.sh` okunmadı.
