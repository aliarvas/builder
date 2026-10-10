# T-002 review (prompts.py + docs/PROMPTS.md)

**Reviewer:** claude-reviewer · **Kapsam:** `tasks/T-002-prompts-readable.md`; `builder/prompts.py`, `builder/workflow.py` ve `builder/build.py` değişiklikleri, `docs/PROMPTS.md`, `tests/test_vertical_slice.py` (`PromptDocumentationTests`), `AGENTS.md` satırı. T-003 kaynaklı değişiklikler kapsam dışı bırakıldı.
**Karar: merge edilebilir.** Bloklayıcı bulgu yok; aşağıdaki düşük/orta notlar T-003 veya sonraki bir temizlikte kapatılabilir.

## Gözlemler (kanıt)

- `python3 -m unittest`: 23 test geçti (3.14).
- **`--print` byte-identical.** HEAD (`f838f82`, T-001) çıktısını scratchpad'e `git archive` ile açıp aynı komutu çalıştırdım ve `cmp` ile karşılaştırdım:
  - Brief A + kit OpenAPI: **özdeş** (SHA-256 `28bb5bc8…` her iki tarafta, 26.174 bayt).
  - Brief A + Brief B + kit OpenAPI: **özdeş**.
- **Token tahmini doğru.** Karakter ÷ 4 (yukarı yuvarlama), `{brief_text}` çıkarıldıktan sonra: `PHONE_AGENT_SYSTEM_PROMPT` 114 karakter → ~29; `PHONE_AGENT_TASK_MESSAGE_TEMPLATE` 374 karakter → ~94. `docs/PROMPTS.md` ile birebir uyuşuyor.
- **OVER BUDGET işareti doğru (Brief A için).** Gerçek adım toplamı (system + task, Brief A) 10.662 karakter ≈ **2.665 token**; Brief A+B ≈ **3.264 token**. İkisi de 1.500 üstünde (bkz. bulgu 1: işaret hesaplanmıyor, elle konmuş).
- `docs/PROMPTS.md` üretilenle birebir aynı (`generate_prompt_doc() == dosya` → True). Başlık metni, bölüm başına ad/amaç/alıcı/kullanıldığı yer/metin, görünür yer tutucu ve deterministik çıktı (zaman damgası yok) gereksinimleri karşılanıyor.
- `AGENTS.md`: tam olarak istenen tek satır eklenmiş (reading map).
- Freya'ya istek atılmadı, kod değiştirmedim.
- **Süreç notu (kendi hatam):** `docs/PROMPTS.md`'nin güncel olduğunu denerken `python3 -m builder.prompts` komutunu çalıştırdım; bu komut dosyayı yeniden yazar. Yazmadan önce ve sonra `generate_prompt_doc()` ile dosya içeriği eşitti (True), yani içerik değişmedi, yalnızca değiştirilme zamanı güncellendi. "Kod/dosya değiştirme" kuralına aykırı bir adımdı; tekrarlamayacağım (kontrol için yalnızca fonksiyonu import edip karşılaştıracağım).

## Bulgular (önem sırasıyla)

### 1. [Orta] `over_budget` elle yazılmış bayrak; bütçe tanımıyla (adım toplamı) örtüşmüyor
- `builder/prompts.py:20,52` (`over_budget=True`), `:90-98` (doc üretimi).
- Bütçe tanımı (`docs/ARCHITECTURE.md` Prompt budget, `docs/DEFINITION-OF-DONE.md:22`): `system_prompt + role_message + task_message` adım başına 500–1.500 token. Doc ise her prompt'u ayrı ölçüyor: sistem prompt'u "~29" gösteriliyor (alt sınırın altı gibi görünüyor), şablon "~94 static + brief". Adım toplamı hiçbir yerde gösterilmiyor.
- `OVER BUDGET` ifadesi bugün Brief A için doğru, ama koddan türetilmiyor: kısa bir brief ile aşılmaz, çok kısa bir adımda da alt sınırın (500) altı kontrol edilmez.
- **Düzeltme (T-003 veya builder-side ölçüm görevi):**
  - Bayrak yerine `inserts_full_brief: bool` gibi bir açıklama alanı kullan; "OVER BUDGET" metnini yalnızca bu alan doluyken ve "Brief A ≈ …" gibi ölçülmüş bir örnekle birlikte yaz.
  - Doc'a "Step total (system + task, static) ≈ N" satırı ekle.
  - Gerçek denetim (DoD'daki "builder check, reported in the trace") `build_workflow` çıktısındaki adım başına `system_prompt + role_message + task_message` uzunluğunu ölçüp trace'e yazmalı ve bütçe dışındaysa bölmeli/hata vermeli.

### 2. [Düşük] Phone agent'ın okuduğu araç açıklama parçaları `prompts.py` dışında
- `builder/tools_from_openapi.py:137` (`"Call this API operation."`) ve `:143` (`"Fields: "`).
- Bunlar tool `description` olarak phone agent'a gidiyor, ancak `docs/PROMPTS.md`'de görünmüyor. T-002 hedefi "builder'ın kullandığı her prompt metni tek yerde". Küçük ama ilkeyi deliyor; T-004+ "CALL it when…" tetikleyicileri gelince daha da önemli olacak.
- **Düzeltme:** bu iki parçayı `PromptDefinition` olarak `prompts.py`'ye taşı (receiver: `phone agent`, used at: `tools_from_openapi.py — tool description`) ve oradan render et. `_closing_transition` açıklaması (`workflow.py`, `"close_call succeeded"`) routing içindir, prompt sayılmaz; ama yorum satırı eklenebilir.

### 3. [Düşük] Test sabit sayı varsayıyor ve bütçe mantığını denetlemiyor
- `tests/test_vertical_slice.py` `test_prompt_document_exposes_token_budget`: `assertEqual(2, document.count("- Approximate tokens:"))` yeni bir prompt eklendiği anda (T-003 planlıyor) boş yere kırılır. `assertIn("**OVER BUDGET**", ...)` yalnızca metnin varlığını sınıyor.
- **Düzeltme:** sayıyı `len(PROMPTS)` ile karşılaştır. Bütçe mantığı (bulgu 1) koddan hesaplanır hale gelince, "uzun brief → OVER BUDGET, kısa brief → değil" davranışını sınayan bir test ekle.

### 4. [Düşük] PROMPTS.md iki farklı süslü parantez biçimini açıklamıyor
- `docs/PROMPTS.md`: `{{customer_id}}` (Freya çağrı değişkeni, çağrı anında dolar) ve `{brief_text}` (builder yer tutucusu, build anında dolar) aynı blokta görünüyor. Teknik olmayan okuyucu (kullanıcı) için karışık.
- **Düzeltme:** `generate_prompt_doc()` başlığına tek cümle ekle: "`{{name}}` Freya fills at call time; `{name}` the builder fills at build time." (Test `PROMPTS.md`'yi karşılaştırdığı için yeniden üretmek yeterli.)

### 5. [Düşük] Token tahmini kaba (karakter ÷ 4)
- Doğru uygulanmış ve doc'ta "characters ÷ 4" diye etiketli. Ancak tablolu/biçimli İngilizce brief'lerde gerçek sayı genelde daha yüksektir (≈ ÷3.2–3.5). Brief A için bile 2.665 → ~3.200 olabilir.
- **Öneri:** trace'te "tahmini" olduğunu belirt ve karar sınırında (1.350–1.500) güvenlik payı bırak. Kesin sayı gerekirse ayrı bir sayım yöntemi (T-003+).

### 6. [Bilgi] `build.py` içe aktarma değişikliği (kapsam notu)
- `builder/build.py:17-24`: script yolunda artık `from builder import freya`, `sys.path` repo kökünü gösteriyor. T-002 kapsamında listelenmemişti ama gerekli: `workflow.py` artık `from .prompts import …` kullanıyor, yani üst düzey `import workflow` ile çalışmaz. `python3 builder/build.py … --print` hem Brief A hem A+B için çalışıyor; kabul.
- Bilgi olarak: `str.replace("{brief_text}", brief_text)` tek geçişli, brief içinde aynı yer tutucu metni olsa da yeniden yerine konmuyor (`'x {brief_text} …'` denemesi doğrulandı). İleride birden fazla yer tutucu eklenirse sıralı `replace` yerine tek geçişli `re.sub` kullanılmalı (brief metni sonraki bir yer tutucuyu içerirse yanlış yerine koyma olur).

## Doğrulananlar

- Brief değeri yok: prompt metinleri nötr ("bank's digital assistant", call variable adları, tool-use kuralı); yalnızca yer tutucu.
- `render_phone_agent_*` çıktısı eski satır içi birleştirmeyle aynı (byte-identical kanıtı yukarıda).
- Python 3.10+/stdlib: `dataclasses`, `math`, `pathlib`; 3.10'da kırılacak sözdizimi yok.
- Üretici hem `python3 -m builder.prompts` hem `python3 builder/prompts.py` ile çalışabilir; yol `__file__`'dan hesaplanıyor.
- Freya yok, testler çevrimdışı.
- Prompt bütçesi kuralına uyum: T-002 yeni bir adım eklemiyor; mevcut tek adım bütçeyi aşıyor (T-001 tasarım gereği), bu doc'ta "OVER BUDGET" olarak dürüstçe işaretli.
