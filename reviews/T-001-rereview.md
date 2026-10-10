# T-001 re-review (fix turu)

**Reviewer:** claude-reviewer · **Kapsam:** `reviews/T-001-review.md` bulgularının doğrulanması; `builder/*.py`, `tests/test_vertical_slice.py`
**Karar: merge edilebilir** (aşağıdaki "yeni bulgular" için T-002'ye alınacak notlarla; bloklayıcı yok). Ön koşul yok. N2 (yeni şema anahtarlarının Freya tarafından kabulü) yalnızca kullanıcı onayıyla bir dry run ile doğrulanabilir; onaylanana kadar açık risk olarak kalır.

## Gözlemler

- `python3 -m unittest` (3.14): 21 test geçti. `python3.11 -m unittest`: 21 test geçti. 3.10 yorumlayıcısı makinede yok; söz dizimi 3.10'a uygun.
- `builder/freya.py`, `build-the-builder-v2/freya.py` ile birebir aynı (diff boş), `AGENT_LLM` değişmemiş.
- `python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json --print`: stdout saf JSON, stderr'e `print: ok (slot=brief-a, nodes=2, tools=7)`.
- Freya'ya istek atılmadı, kod değiştirilmedi.

## Önceki bulguların doğrulanması

| # | Durum | Kanıt |
|---|---|---|
| 1 | **Kapandı** | `trace.py` → `builder/run_trace.py`. `builder/build.py:14-24` paket (`from . import`) ve script (`sys.path.insert`) yolunu ayırıyor. `CLITests.test_main_print_is_importable_network_free_and_stdout_is_json` (`tests/test_vertical_slice.py:346`) `build.main([...,"--print"])`'ı doğrudan çağırıyor. |
| 2 | **Kapandı** (N1/N2 notlarıyla) | `tools_from_openapi.py:64-127`: `enum`, `pattern`, `minimum`/`maximum`, `minLength`/`maxLength`, `minItems`/`maxItems`, `items`, iç içe `properties`/`required`, `allOf`/`oneOf`/`anyOf`, `nullable` kopyalanıyor; `format` açıklamaya ekleniyor. Gerçek çıktı: `create_promise.date` → `"description": "(format: date)"`. Testler: `:113` (iç içe/dizi/kısıt), `:178` (`$ref`). |
| 3 | **Kapandı** | `tools_from_openapi.py:168-175`: ad `re.sub(r"[^A-Za-z0-9_]+","_")`, çakışmada `OpenAPIError`, path-item `parameters` açık hata. Testler: `:154`, `:165`. |
| 4 | **Kapandı** | `tools_from_openapi.py:187`: baked call variable'lar `required`'dan çıkarılıyor. Gerçek çıktı: `create_promise.required = ["product_id","amount","date"]`. Sentetik test `:110`: `["client_ref","choice_v2","extra_count"]`, `customer_id` baked (`:107`). |
| 5 | **Kapandı** | `build.py:100-107` (mod başına `.print.log` / `.validate.log` / `.log`), `:170-183` (hatalar `traces/<slot>.failed.log`), `:176-185` (`BaseException` + `finally: trace.finish`). Slot trace'te (`:125`), published version trace'te (`:163`). Testler: `:374` (iyi trace ezilmez), `:393` (KeyboardInterrupt), `:407` (girdi hatası). |
| 6 | **Kapandı** | `build.py:69-97` `_ensure_published_version`: en yeni sürüm yayında değilse publish eder, tekrar okuyup doğrular, olmazsa hata verir; `export_workflow`'dan önce çağrılıyor (`:159-160`). Testler `:418-438` (3 senaryo). Canlı create yolu henüz gerçek Freya'da denenmedi (aşağıda not). |
| 7 | **Kapandı** | `.gitignore:18` `.freya-agents.json`. `docs/ARCHITECTURE.md:82` taze checkout'ta yeni workflow açıldığını ve workflow limitini belgeliyor. |
| 8 | **Kapandı** | `workflow.py:57-61`: son geçiş `always` → `call`. Test `:249`. |
| 9 | **Kapandı** | `run_trace.py:16,28-33` ve `build.py:110-117`: `fak_...` deseni maskeleniyor, hata metni 300 karakterle kısalıyor. Testler `:301`, `:387`. |
| 10 | **Kapandı** | `WorkflowTests` artık gerçek 7 araçlı kit OpenAPI'siyle çalışıyor (`:232-238`); `null`/`agent_config`/`name==key`/`tools yalnızca conversation` (`:240-247`), `"true"`/`"True"` operandları (`:249-256`), CLI ve publish testleri eklenmiş. Not: `end_call` ulaşılabilirlik testi hâlâ yalnızca varlığı denetliyor; `close_call` koşulu ayrı testle kapsandığı için kabul. |
| 11 | **Ertelendi (T-002)** | Bilinçli erteleme. T-002'de baked-alan/değişken çakışma denetimi ve araç açıklamalarındaki "CALL it ..." tetikleyicisi yapılacak. |
| 12 | **Kapandı** | `build.py:150` `validate: ok (slot=..., nodes=..., tools=...)` stdout'a; `:165-168` `save: ok (workflow_id=..., agent_id=..., published_version=..., export=..., trace=...)`; `--print` özeti stderr'e (`:141-144`). Test `:361`. Anahtar/env değeri yazdırılmıyor. |

## Yeni bulgular (önem sırasıyla)

### N1. [Orta] Beklenmedik OpenAPI şeması tüm build'i düşürüyor (hidden tool dosyası riski)
- `tools_from_openapi.py:88-94`. Denenen girdiler:
  - `{"type": ["string","null"]}` (OpenAPI 3.1) → `TypeError: cannot use 'list' as a set element`. `OpenAPIError` değil, yani `build.py:170` yakalamıyor; `BaseException` yolundan rc=1 ile çıkıyor.
  - `{"enum": ["a","b"]}` veya `{}` (tipsiz alan) → `OpenAPIError: OpenAPI type is required`.
- Gizli tool dosyası "farklı" gelecek; alan tipini yazmamış tek bir alan yüzünden build'in sıfır puanla bitmesi, eski davranıştan (`string`'e düşme) kötü.
- **Düzeltme (T-002 başında küçük iş):**
  - `type` liste ise `"null"` dışındakini al, `nullable: true` ekle.
  - `type` yoksa `enum` varsa `string`, yoksa `string` kullan ve trace'e `warning:` satırı yaz; durdurmak yerine devam et.
  - `TypeError`'ı da `OpenAPIError`'a sarmala. Path-item `parameters` için de hata yerine uyarı + yok sayma düşünülebilir (query/path parametresi body'ye eklenmediği için sonuç eksik tool olur; trace'te görünür kalsın).
  - Testleri buna göre güncelle (`test_missing_server_and_unknown_type_fail`).

### N2. [Orta, doğrulama] Yeni şema anahtarları Freya dry run'ında denenmedi
- Yeni anahtarlar (`pattern`, `minimum`, `nullable`, `minLength`, `allOf`/`oneOf`, `items`) sentetik OpenAPI ile üretilebilir. Kit OpenAPI'si bunların yalnızca `format` açıklamasını ve filtrelenmiş `required`'ı kullanıyor, yani kit çıktısı önceki dry-run'dan çok az farklı.
- Platformun bilinmeyen JSON-schema anahtarlarını reddedip reddetmediği bilinmiyor.
- **Öneri:** Freya kuralı gereği ben istek atmıyorum; CTO kullanıcıdan onay alırsa düzeltmeli kodla tek bir `--validate` (dry run, kayıt yok) ve gerekirse bu anahtarları içeren sentetik bir OpenAPI ile bir dry run çalıştırılabilir. Onay yoksa kodda savunmacı davran: bilinmeyen/desteklenmeyen anahtarları (`pattern`, `nullable`, `allOf`/`oneOf` vb.) şemaya koymak yerine açıklamaya taşı. Dry run reddederse aynı süzme zorunlu olur.

### N3. [Düşük] `traces/` ve `submission/` yolları CWD'ye bağlı; test amaçlı loglar commit'e girebilir
- `build.py:100-107,157`: `Path("traces")`/`Path("submission")` göreli. Komut başka dizinden çalıştırılırsa çıktı orada oluşur (sözleşme repo kökünden çalıştırmayı varsayıyor, kit'in `.freya-agents.json`'u da CWD'de).
- `.gitignore` `*.print.log`, `*.validate.log`, `*.failed.log` için kural içermiyor; `traces/` şu an untracked ve `brief-a.print.log`/`brief-a.validate.log` içeriyor. Teslimat için yalnızca gerçek koşu trace'i (`<slot>.log`) commit edilmeli.
- **Düzeltme:** `.gitignore`'a `traces/*.print.log`, `traces/*.validate.log`, `traces/*.failed.log` ekle (veya commit öncesi temizle). Kökü `Path(__file__).resolve().parent.parent` ile sabitlemek isteğe bağlı.

### N4. [Bilgi] Canlı doğrulama bekleyen noktalar (kod hatası değil)
- Create yolundaki publish (bulgu 6) gerçek Freya'da henüz denenmedi; testler sahte `freya.api` ile çalışıyor. Kullanıcı onaylı ilk gerçek save koşusunda (önce chat testi, voice yalnızca chat geçtikten sonra) `published_version`'ın sayı döndüğü ve `export` dosyasının yazıldığı teyit edilmeli.
- `traces/brief-a.validate.log` önceki (onaylı) dry run'dan kalma; sonraki dry run onaylanırsa içeriği gözden geçirilmeli (model çağrısı ve self-test satırları "none").

## Karar: merge edilebilir
Bulgular 1-10 ve 12 kanıtla kapandı; 11 bilinçli olarak T-002'de. N1 ve N2 bloklayıcı değil ama hidden tool dosyası riski taşıdığı için T-002'nin ilk işi olmalı; N2 onay gerektiren bir doğrulamadır, merge'i bloklamaz. N3 commit öncesi temizlik.

## Kural uyumu (Freya isteği yok, test sırası)

- Bu re-review sırasında Freya'ya hiçbir istek atılmadı; yalnızca çevrimdışı `unittest` ve `--print` çalıştırıldı.
- Testler çevrimdışı: `freya.api` sahte (`patch`), `CLITests` geçici dizinde çalışıyor. Kod chat/simülasyon çağırmıyor (T-001 kapsamı dışı).
- İlk turda yazdığım "CTO `--validate` çalıştırsın" önerisi yeni kuralla çelişiyordu; yukarıda onay şartına çevrildi.
