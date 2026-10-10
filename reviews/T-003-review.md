# T-003 review (hardening: tolerant OpenAPI, tool triggers, post-hook)

**Reviewer:** claude-reviewer · **Kapsam:** `tasks/T-003-hardening.md`; `builder/tools_from_openapi.py`, `builder/prompts.py` (system prompt eki), `builder/build.py` (uyarıların trace'e yazılması), `tests/test_vertical_slice.py` (T-003 testleri), `docs/PROMPTS.md`. T-004 kaynaklı değişiklikler değerlendirilmedi.
**Karar: düzeltme gerekli (küçük).** Görev metnine uyum iyi (29 test geçiyor, build artık çökmüyor), ama post-hook'un "başarılı" cümlesi dürüstlük önceliğini (AGENTS.md madde 4) deliyor ve F-010'un asıl davranışını karşılamıyor (bulgu 1, 2). İki düzeltme küçük ve genel kalır; T-004 identity adımı bu hook'a yaslanacağı için T-004 öncesi yapılmalı.

## Gözlemler (kanıt)

- `python3 -m unittest`: 29 test geçti. `docs/PROMPTS.md` üretilenle birebir aynı (import ederek karşılaştırdım, dosya yazmadım).
- Hook kodu `compile()` ediliyor, içinde `{{`/`}}` yok, `try/except` + `isinstance` var, `header` çıkarılıyor. Örnek zarflar üzerinde çalıştırdım (offline):

| Girdi | `what_to_do_next` |
|---|---|
| `ok: true`, 200 | "The action succeeded. Now speak…" ✔ |
| `ok: false`, 200 | "NOT carried out…" ✔ |
| HTTP 500 (`data` dict veya `None`) | "NOT carried out…" ✔ |
| `ok: "False"` (string) | "NOT carried out…" ✔ |
| `ok: true, verified: false, wrong_answers_left: 2` | "The action **succeeded**. Now speak…" ✘ |
| `data: {error: "unknown product_id"}` (`ok` yok) | "The action **succeeded**…" ✘ |
| `status: "error"`, `data: None`, `status_code` yok | "The action **succeeded**…" ✘ |
| `result` dict değil | dokunmuyor, hata yok ✔ |

- Kit OpenAPI'si için uyarılar: yalnızca iki `format` taşıması. Şemada yalnızca izinli anahtarlar (`type`, `description`, `enum`, `default`, `items`, `properties`, `required`) kalıyor.
- Freya'ya istek atılmadı, kod/dosya değiştirmedim.

## Bulgular (önem sırasıyla)

### 1. [Yüksek] Post-hook, "ok: true ama olumsuz" sonuçta "başarılı" diyor → F-010 karşılanmıyor
- `builder/tools_from_openapi.py:17-39`.
- F-010'un çekirdeği: yanlış cevap sonrası araç `ok: true, verified: false` döner (işlem yapıldı, ama kontrol başarısız). Hook yalnızca `ok == false` veya HTTP hatasında olumsuz cümle yazıyor. `verified: false` için modele **"The action succeeded. Now speak to the customer or call the next required tool."** deniyor. Bu, F-010'daki "negatif sonucu yok sayıp sonraki soruya geçme" hatasını kuvvetlendirir. Genel bir hook alan adlarını bilemez ama **herhangi bir `false` alanını** yakalayabilir.
- **Teoride karşılıyor mu: hayır, kısmen.** Hook şunları karşılar: `ok: false`, HTTP hatası, tekrar çağrılabilir hata. Şunları karşılamaz: `ok: true` + `verified/all_verified: false`, `hint` içeren sonuçlar, sayaç (`wrong_answers_left`) içeren olumsuz sonuçlar. Platformun "negatif sonuçta sessizlik/yok sayma" sorununun yarısı bu türde.
- **Düzeltme (genel, brief/araç adı yok):** başarılı dalda `data`'daki `False`/`"false"` değerli tüm anahtarları (`ok` hariç) topla; varsa cümle şöyle olsun: `"The action ran, but these result fields are false: verified. Treat each as NOT satisfied; do not proceed as if it passed. Read every field of the result before speaking."` Hiç false alan yoksa mevcut olumlu cümle kalabilir ama "succeeded" yerine "ran" demek (örn. `"The action ran and returned ok. Now speak…"`) daha güvenli. Kalan alanlar (`hint`, sayaçlar) için "Use the other result fields exactly as returned; do not invent values." eklenebilir. Sonra hook testine `ok:true, verified:false` zarfı eklenmeli.

### 2. [Orta] `ok` alanı yoksa veya zarf `status: "error"` ise hook "başarılı" diyor
- `tools_from_openapi.py:24-36`. `ok` yoksa `ok_failed` False; `status_code` yoksa `http_failed` False; `result["status"] == "error"` hiç bakılmıyor → üç satır yukarıdaki tabloda ✘.
- Başarısız bir `create_promise` için "action succeeded" demek, AGENTS.md madde 4'ü (araç başarısızken başarı iddiası) doğrudan ihlal eder. Gizli bank API'sı "ok false" sözleşmesinden sapabilir (farklı hata gövdesi).
- **Düzeltme:** başarıyı pozitif koşula bağla. Başarılı say yalnızca: `status` 'success' (veya yok değilse) **ve** (`ok` True/'true' **ya da** `ok` hiç yok ve `error` anahtarı yok) **ve** HTTP 2xx. `error` anahtarı dolu, `status == 'error'`, `data` dict değil ve `status_code` yok → olumsuz cümle. `ok` alanı hiç yoksa nötr cümle: "Check the result fields; do not claim success unless they clearly show it."

### 3. [Orta] Olumsuz cümle "hatayı açıkla" diyor; brief yeniden denemeyi istiyorsa çelişir
- `tools_from_openapi.py:34`: `"…explain the failure to the customer."`
- Kit Brief A kuralı: kayıt başarısızsa bir kez daha dene, tekrar başarısızsa kapat (PUB-10 hata enjeksiyonu). Hook "açıkla" derse model denemeden vazgeçip özür dileyebilir (tek denemede pes). API açıklaması da "500: nothing was recorded. The call may be repeated" diyor.
- **Düzeltme (genel):** `"The action was NOT carried out. Do not say it was done. Follow the brief's rule for a failed action (retry if the brief allows it, otherwise tell the customer plainly)."`

### 4. [Orta] Araç açıklamaları özeti iki kez içeriyor ve tetikleyici cümle bozuk İngilizce
- `tools_from_openapi.py:246-258`. Gerçek çıktı:
  `get_account`: "The late products. Refused until both questions are passed. CALL this tool to The late products. Refused until both questions are passed. Saying you did it is not enough."
  `verify_identity`: özet iki kez + "Fields: …" (token şişmesi, 7 araçta ~ +%40).
  `create_promise`: "Fields: date: format: date".
- Özet cümle halinde olduğu için "CALL this tool to <özet>" gramer olarak çalışmıyor ve çok cümleli özetlerde saçma. Şablon "özeti tekrar etmeden" yazılmalı.
- **Düzeltme:** `parts = [summary, "CALL this tool whenever the situation above applies; saying you did it is not enough."]` (özeti tekrar etme) veya `f"{summary} CALL this tool for this action; saying you did it is not enough."`. `Fields:` listesinde yalnızca kendi açıklaması olan alanları (zaten öyle) tut ve `date: format: date` gibi tekrar edenleri `format: date` olarak yaz.

### 5. [Orta] `allOf`/tipsiz `properties` şemaları bilgiyi yitiriyor veya tutarsız çıktı üretiyor
- `tools_from_openapi.py:134-155,186-193,195-209`. Denemeler:
  - `{"allOf":[{"type":"object","properties":{"q":…},"required":["q"]}]}` → `type: "string"`, `description: "allOf: [{...}]"` (JSON olarak, 240 karakterde kesilebilir). `allOf` gerçek spesifikasyonlarda `$ref` ile çok yaygın; alan yapısı (`q`) tamamen kayboluyor ve model nesneyi string olarak yazar.
  - `{"properties": {"z": {"type":"integer"}}}` (tipsiz) → `type: "string"` ama `properties` var: tutarsız şema (Freya dry run bunu reddedebilir, reddetmese de model yanlış doldurur).
  - `example`, `x-*`, `title` gibi gürültü anahtarları açıklamaya giriyor (`x-extra: {"a":[1,2,3]}`); token israfı, modele hiçbir faydası yok.
- **Düzeltme:** (a) `allOf` varsa alt şemaları birleştir (`properties`, `required`, `type`, `description`) ve sonra normal kopyala; `oneOf/anyOf` için "one of: …" kısa düz cümle. (b) `properties` varsa tipi `object`, `items` varsa `array` çıkar; çakışırsa uyarı. (c) Açıklamaya taşınacak anahtarları bir izin listesiyle sınırla (`format`, `pattern`, `minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, `maxItems`, `multipleOf`, `exclusiveMinimum/Maximum`); `example`, `x-*`, `title`, `xml`, `externalDocs`, `readOnly` vb. at (gerekirse tek satır "example: …" tutulabilir).

### 6. [Düşük] Çakışma yeniden adlandırması varsayılan çağrıda hiç çalışmıyor
- `tools_from_openapi.py:225-243,281-282`. `baked_fields` ve `known_entry_variables` varsayılanı aynı küme (`CALL_VARIABLES`); `build.py` ikisini de geçmiyor. Yani `name in known_entry_variables and name not in baked_fields` dalına CLI'dan ulaşılamıyor; yalnızca testte (`:329`) özel kümelerle çalışıyor. T-004'te extraction değişkenleri girince işe yarayacak, şimdilik ölü kod.
- **Düzeltme:** T-004'te `build_workflow` çağrısında gerçek extraction/giriş değişkenlerini `known_entry_variables` olarak geçir ve bu bağlantıyı test et.

### 7. [Düşük] OpenAPI'nin iç içe `default` değeri şemada kalıyor
- `tools_from_openapi.py:218-219`. Üst düzey alanlarda yer tutucu bunu eziyor, ama iç içe (`items`/`properties`) alanlarda OpenAPI'deki `default` olduğu gibi kalıyor; Freya bunu "baked" sayar ve model alanı görmez.
- **Düzeltme:** iç içe alanlarda `default`'u atla veya açıklamaya taşı ("default: …").

### 8. [Düşük] Sistem prompt'unda tekrar
- `prompts.py`: "After every tool result, speak to the customer or call the next required tool." hem sistem prompt'ta hem task şablonunda. ~25 token boşa (bütçe zaten tek adımda aşılıyor). Bir yerde bırak.

## T-002 review notlarının durumu

| T-002 notu | T-003 ile durum | Kanıt |
|---|---|---|
| 1. `over_budget` elle bayrak, adım toplamı ölçülmüyor | **Kapanmadı** | `prompts.py:23,55`: bayrak hâlâ elle `True`. |
| 2. Phone agent'a giden araç açıklama parçaları `prompts.py` dışında | **Kapanmadı, kötüleşti** | Tetikleyici şablon, `Fields:` ve hook cümleleri (`what_to_do_next`) `tools_from_openapi.py:17-39,246-258`'te satır içi; hiçbiri `PROMPTS.md`'de yok. Phone agent'ın gördüğü yeni metinler: ≥3. |
| 3. Sabit `assertEqual(2, …)` | **Kapanmadı** | `tests/test_vertical_slice.py:601` hâlâ `2`; yeni bir prompt eklenince kırılır. |
| 4. PROMPTS.md'de `{{x}}` / `{x}` açıklaması | **Kapanmadı** | Başlıkta açıklama yok. |
| 5. Karakter ÷ 4 kaba tahmin | **Kapanmadı** (T-003 kapsamı dışı) | — |
| 6. (bilgi) tek geçişli yer tutucu | Geçerli, değişiklik yok | — |

Yani 5 notun **hiçbiri** T-003 ile kapanmadı; görev metni de bunları kapsamıyordu. Not 2 yeni phone-agent metinlerinin eklenmesiyle büyüdü; hook ve açıklama cümleleri `prompts.py`'ye taşınmalı (bulgu 1-4 düzeltmeleriyle birlikte yapılırsa tek dokunuşla biter, PROMPTS.md'de de görünür).

## Doğrulananlar

- Görev kapsamı 1: liste tipi → ilk desteklenen tip + `nullable` açıklamaya; tipsiz → `string`/enum tipi + `warning:`; alan bazında `try/except`; yalnızca `servers[0].url` eksikliği fatal; path-item `parameters` uyarı + yok sayma; desteklenmeyen anahtarlar açıklamaya, şemada yalnızca izinli anahtarlar. Uyarılar `trace`'e `warning:` satırı olarak yazılıyor (`build.py`, test `test_openapi_warnings_are_written_to_trace`).
- Görev kapsamı 2, 3, 4, 5, testler: mevcut ve geçiyor (bulgular 1-6 kalite/dürüstlük iyileştirmeleri, spesifikasyona aykırılık değil). Hook genel metinli, araç adı/brief değeri içermiyor.
- Trace uyarı metinleri anahtar içermiyor (alan yolları ve tip adları).
- Freya yok, testler çevrimdışı.
- Prompt bütçesi: `call` adımı Brief A için hâlâ ≈ 2.7k token (system ~76 + task ~94 + brief). T-004 ile adımlara bölününce 500–1.500 aralığı denetlenecek.
