# T-001 review (vertical slice)

**Reviewer:** claude-reviewer · **Kapsam:** `builder/*.py`, `tests/test_vertical_slice.py`, `tasks/T-001-vertical-slice.md`
**Karar: düzeltme gerekli.** Merge öncesi en az bulgu 1, 2, 5, 6 ve 7 kapanmalı; 3, 4, 8 ve 10'un temel kısmı aynı turda yapılabilir. Düzeltmelerden sonra yeniden review.

## Gözlemler

- `python3 -m unittest`: 5 test geçti (Python 3.14; 3.10'da koşturulmadı, söz dizimi 3.10'a uygun görünüyor).
- `python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json --print` çalışıyor.
- `builder/freya.py`, `build-the-builder-v2/freya.py` ile birebir aynı (diff boş), `AGENT_LLM` değişmemiş.
- Brief veya OpenAPI değeri koda gömülmemiş. Tek sabit isimler `close_call` ve 5 call variable (spec'te izinli). Brief metni yalnızca `build_workflow` argümanı olarak geçiyor.
- CTO'nun bildirdiği `--validate` (Freya dry run) geçti. Tek eksik: komut başarıda ekrana hiçbir şey yazmıyor (bkz. bulgu 12).
- Freya'ya istek atılmadı, review sırasında dosya değiştirilmedi.

## Bulgular (önem sırasıyla)

### 1. [Yüksek] `trace.py` stdlib `trace` modülünü gölgeliyor; `build.py` paket olarak import edilemiyor
- `builder/build.py:14-17`: düz `import freya`, `from trace import ...`, `from workflow import ...`. Yalnızca `python3 builder/build.py` ile çalışır (script dizini `sys.path[0]`).
- `python3 -c "import builder.build"` → `ModuleNotFoundError: No module named 'freya'`. Testler `builder.trace` gibi paket yoluyla import ediyor, `build.main` hiç test edilmiyor; testler bu yüzden yeşil.
- Script dizinindeki `trace.py`, stdlib `trace` yerine yüklenir; başka bir stdlib modülü `trace` import ederse bozulur.
- **Düzeltme:** `trace.py` → `run_trace.py` olarak yeniden adlandır. `build.py` başına `sys.path.insert(0, str(Path(__file__).resolve().parent))` ekle (sözleşme `python3 builder/build.py` olduğu için bu yol daha güvenli; alternatif `from builder import ...` + `python3 -m builder.build`). `main(["a.md","t.json","--print"])`'ı doğrudan çağıran bir test ekle.

### 2. [Yüksek] OpenAPI kısıtları düşüyor
- `builder/tools_from_openapi.py:63-73`: yalnızca `type`, `enum`, `description` kopyalanıyor.
- Kit dosyasında `create_promise.date` için `format: date` var, `description` yok → modele çıplak `string` gidiyor. Gizli tool dosyasında bu tür kısıtlar artar.
- Kaybolanlar: `format`, `pattern`, `minimum`/`maximum`, `items`, iç içe `properties`, `allOf`/`oneOf`, `nullable`.
- **Düzeltme:** `format`, `pattern`, `minimum`, `maximum` değerlerini `description` sonuna ekle (ör. `"(format: date)"`). `array` için `items`'ı, `object` için `properties`'i kopyala. Bilinmeyen tiplerde sessizce `string`'e düşme; açık hata ver veya uyarı yaz.

### 3. [Orta] Tool adı path'ten ham alınıyor
- `builder/tools_from_openapi.py:107`: yalnızca `path.strip("/")`.
- `/v1/verify` veya `/tools/{id}` geçersiz fonksiyon adı üretir (slash, süslü parantez). Aynı ada düşen iki path sessizce çiftlenir. Path-item seviyesindeki `parameters` yok sayılıyor.
- **Düzeltme:** `re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")` uygula; çakışmada `OpenAPIError` fırlat. Path-item `parameters` desteklenmiyorsa belgele.

### 4. [Orta] `required`, baked alanları da içeriyor
- `builder/tools_from_openapi.py:122-123`; test de bunu bekliyor (`tests/test_vertical_slice.py:45`).
- `customer_id` baked olduğu için modele gösterilmiyor ama `required`'da kalıyor. Kit örneği `required`'a yalnızca model alanlarını koyuyor.
- Dry run geçti (CTO), yani bloklayıcı değil. Gerçek simülasyonda model "eksik zorunlu alan" davranışı gösterirse baked alanları `required`'dan çıkar.

### 5. [Orta] Başarısız koşu iyi trace'in üstüne yazıyor; `--print`/`--validate` `traces/`'ı kirletiyor
- `builder/build.py:77`, `builder/trace.py:50-51`: trace her modda `traces/<slot>.log`'a yazılıyor.
- Teslimat trace'i `traces/hidden-1.log` olacak; aynı slotla hatalı bir yeniden koşu doğru trace'i ezer.
- `finish` yalnızca `except Exception` yolunda çağrılıyor; `KeyboardInterrupt`/`SystemExit`'te trace yazılmıyor.
- **Düzeltme:** yalnızca varsayılan (save) modda `traces/<slot>.log` yaz; `--print`/`--validate` için `<slot>.print.log` / `<slot>.validate.log` kullan veya hiç yazma. Hatalı koşuyu `<slot>.failed.log` olarak yaz. `try/finally` ile her çıkışta `finish` çağır. Slot adını ve sürüm numarasını trace'e ekle.

### 6. [Orta] İlk create sonrası publish doğrulanmıyor
- `builder/build.py:55-65, 101-108`, `builder/freya.py:36-47`.
- `update_workflow` publish ediyor; ilk `create_workflow` etmiyor (API doc: "update does NOT publish"; create için bir şey söylemiyor). `_published_version` yalnızca okuyor, `isPublished` yoksa "unknown" dönüyor.
- **Düzeltme:** `export_workflow`'dan önce `GET /api/v2/versions/workflow/{id}` ile en yeni sürümün `isPublished` olduğunu doğrula; değilse `POST .../publish {versionId}` çağır, olmazsa hata ver. CTO'nun gerçek (save) koşusunda doğrulaması önerilir.

### 7. [Orta] `.freya-agents.json` repo kökünde yaratılıyor ve ignore edilmiyor
- `freya.save_workflow` state dosyasını CWD'ye yazar. `.gitignore` yalnızca `build-the-builder-v2/.freya-agents.json`'u kapsıyor. Secret değil ama commit'e girer ve sonraki koşuyu "update" moduna sokar.
- **Düzeltme:** `.gitignore`'a `.freya-agents.json` ekle. Taze checkout'ta her koşunun yeni workflow açtığını `docs/ARCHITECTURE.md`'ye yaz (workflow limiti: sayfada 10, kit'te 200).

### 8. [Düşük] `call` node'unda `always` fallback yok
- `builder/workflow.py:55`. Facts dokümanı "A node needs an `always` fallback" diyor; `workflow-format.md` self-transition'ı öneriyor.
- **Düzeltme:** transitions sonuna `{"target_node": "call", "description": "Keep going", "condition": {"operator": "always"}}` ekle.
- `max_node_turns: 60` / `max_turn_transition: "hang_up"` doğru çiftlenmiş; ancak sınıra gelince `close_call` olmadan hang_up'a gitmek outcome/dürüstlük riski (sonraki görev).

### 9. [Düşük] Trace redaksiyonu yalnızca tam değer eşleşmesi
- `builder/trace.py:28-32`. Başlık/URL'den gelen kısmi sızıntıyı yakalamaz. Şu an yalnızca `str(exc)` yazılıyor ve `freya.api` hata gövdesini 1500 karakterle kesiyor; anahtar yazılmıyor, risk düşük.
- **Düzeltme:** `fak_[A-Za-z0-9_-]+` desenini de maskele. `str(exc)`'i ~300 karakterle kısalt (hata gövdesinde brief/müşteri verisi olabilir).

### 10. [Düşük] Test boşlukları
- `WorkflowTests` yalnızca tek sahte `close_call` aracıyla çalışıyor; gerçek 7 araçlı çıktı için `null`/`agent_config`/`name==key` testi yok.
- Eksik testler: `tools` yalnızca conversation node'unda; `close_call` geçişinin `"true"`/`"True"` operandları; baked `customer_id` ile model alanlarının ayrımı sentetik OpenAPI'de (sentetik testte call variable yok); `$ref` ve `servers` eksik hatası; `--print` ağsız çalışması; slot türetme.
- `tests/test_vertical_slice.py:113-133`: `end_call` ulaşılabilirlik testi `close_call` koşulunun doğruluğunu doğrulamıyor.
- Test `build-the-builder-v2/tools/openapi.json`'u okuyor ve `build-the-builder-v2/` şu an untracked. Commit edilmezse taze checkout'ta test düşer.

### 11. [Bilgi] İleri görevler için notlar
- Çıplak `string` alan adı, node girişinde set edilmiş başka bir değişkenle çakışırsa (ör. extraction değişkenleri) alan baked olup modelden gizlenir. T-002'de çakışma kontrolü şart.
- OpenAPI'de `title` adlı ilgisiz bir alan olursa müşterinin `title` değeriyle baked edilir. Spec'e uygun ama riskli; trace'e uyarı yazılabilir.
- Tool açıklamaları "CALL it only after ..." tetikleyicisi içermiyor; model araç çağırmak yerine sözel onay verebilir. Post-tool sessizliği için `post_process_code` / `what_to_do_next` yok. T-002 konusu.

### 12. [Düşük] `--validate` başarıda hiçbir şey yazmıyor (CTO gözlemi)
- `builder/build.py:92-96`: başarı yalnızca trace dosyasına yazılıyor, stdout boş. CLI'dan başarı/başarısızlık ayırt edilemiyor (yalnızca çıkış kodu).
- **Düzeltme:** her modun sonunda bir özet satırı yazdır (ör. `validate: ok (slot=<slot>, nodes=<n>, tools=<n>)`; save modunda workflow id, agent id, published version, export yolu, trace yolu). Anahtar/env değeri yazdırma. `--print` çıktısı saf JSON kalmalı; özeti stderr'e yaz.

## Doğrulananlar

- `body.properties` yaprak yapısı; her alanda `default`; `enum` ve `required` korunuyor; `const` yok.
- `url`/`method` `default` ile baked; `maxRetries: 0`, `timeoutMs: 10000`; `servers[0].url` kullanılıyor.
- `hang_up`: `end_call`, `on_enter` silent, `message_mode: none`, `transitions: []`, `disable_inactivity_monitor: true`. `close_call_response.data.ok` testi `"true"` ve `"True"` ile OR grubunda.
- `null` ve `agent_config` yok; node `name == key`; `tools` yalnızca conversation node'unda; `test_variables` nötr (`placeholder_customer`, `2000-01-03T12:00`).
- Python 3.10 uyumlu söz dizimi, yalnızca stdlib, secret redaksiyonu temel testi geçiyor.
- `env.sh` (her dizinde) gitignore'da.
