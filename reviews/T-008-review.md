# T-008 review (submission_check.py, trace alanları, SUBMISSION.md)

Rapor: tasks/T-008-report.md. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: tüm paket geçiyor (176). Kapsam: `tools/submission_check.py`, `tests/test_submission_check.py`, `docs/SUBMISSION.md`, `builder/run_trace.py` ve `builder/build.py`'deki trace değişiklikleri (spec.py/workflow.py değişiklikleri T-009, dahil değil).

## Karar: düzeltme gerekli
Kontrolcü gerçek bir dışa aktarımda **hiçbir zaman PASS veremez**: platform dışa aktarılan workflow'a `agent_config` ve yüzlerce `null` varsayılan değer ekliyor, kontrolcü bunları kural ihlali sayıyor (bulgu 1, gerçek `submission/brief-a.workflow.json` üzerinde doğruladım). SUBMISSION.md "her madde PASS olmalı" dediği için teslim kapısı kapalı kalır ya da biri kontrolü gevşetmek zorunda kalır. Küçük düzeltme; ayrıca anahtar taramasında iki zayıflık (bulgu 2, 3). Trace alanları ve redaksiyon doğru.

## Bulgular

### 1. [Yüksek, yanlış FAIL] `export_has_no_null` ve `export_omits_agent_config` platformun eklediği alanlarda hep düşer
- `submission_check.py` `_contains_null(exported)` ve `_contains_key(exported, "agent_config")` tüm dışa aktarım dosyasına bakıyor. Kit'in `export_workflow` fonksiyonu platformdaki workflow'u olduğu gibi yazıyor (`freya.py` satır 65–68) ve kitin `update_workflow` fonksiyonu platformun doldurduğu `agent_config`'i okuyup `llmConfig`'e `AGENT_LLM`'i yazarak yeniden kaydediyor (satır 55–60). Yani yayımlanan her workflow `agent_config` taşır.
- Kanıt (gerçek dışa aktarım `submission/brief-a.workflow.json`, kontrolcünün kendi yardımcılarıyla): `agent_config` var = True; `null` var = True. `null` yolları: tüm node'larda `max_node_turns`, `max_turn_transition`, `passthrough_default_transition` (platform varsayılanları) ve `agent_config` altındaki onlarca ayar (`apiKey`, `baseUrl`, `sttConfig`, ...). İki madde de her teslimde FAIL verir.
- Kural amacı farklı: `workflow-format.md` "agent_config: omit it. The platform fills in defaults" ve "no null" kuralları builder'ın **gönderdiği** tanım içindir. Platformun dışarıya yazdığı dosya bu kuralı sağlayamaz.
- **Düzeltme:** kontrolü gönderilen tanıma taşıyın. En basit: builder, workflow'u kaydetmeden önce kendi çıktısında `agent_config` yokluğunu ve `null` yokluğunu sayıp trace'e yazsın (`sent_agent_config=absent`, `sent_nulls=0`); kontrolcü bu iki satırı doğrulasın. Dışa aktarım için yalnızca ayrışma/kimlik/adım sayısı/anahtar taraması kalsın. (Alternatif: `workflow.agent_config` ve platform varsayılanı olan `max_node_turns`, `max_turn_transition`, `passthrough_default_transition` null'larını yok sayıp geri kalan tanımda null aramak, ama bu platformun varsayılan listesine bağlı, kırılgan.) İlgili testler de gerçek bir platform biçimli dışa aktarımla çalışmalı: şu anki testler yalnızca elle yazılmış temiz dosyalarla geçiyor.

### 2. [Orta] Takım anahtarı taraması yalnızca ortam değişkeni varsa ve bazı biçimlerde çalışıyor
- Takım anahtarı kullanıcının uydurduğu 16+ karakterlik bir sır (`env.example`). Kontrolcü: (a) ortamdaki `FREYA_BANK_TEAM_KEY` değeri metinde geçiyorsa yakalar; (b) `FREYA_BANK_TEAM_KEY=…`/`team_key: …` yazımını 16+ karakter varsa yakalar; (c) `x-team-key`/`authorization`/`x-api-key` başlık adını yakalar.
- Denedim: `FREYA_BANK_TEAM_KEY=abcdefghijklmnop12` yakalandı; ama JSON biçimi `{"team_key": "abcdefghijklmnopqrst"}` (ad ile `:` arasında tırnak) **yakalanmadı**, 16 karakterden kısa değer yakalanmadı, `Bearer <uzun değer>` ve `?apikey=…` biçimleri yakalanmadı. Ortam değişkeni kontrolcünün çalıştığı kabukta tanımlı değilse (b)'nin dışında hiçbir şey yakalanmıyor, ve çıktı yine "PASS no_secrets: no secret patterns or configured secret values" yazıyor; kullanıcı yapılandırılmış değer taramasının atlandığını fark etmez.
- Builder bu anahtarı workflow'a, trace'e veya spec'e yazmıyor (yalnızca `run_cases`/`score` kullanıyor), yani gerçek risk düşük.
- **Düzeltme:** (1) ad–değer deseninde tırnak ve boşluğa izin ver (`["']?\s*[:=]\s*["']?`); (2) ortam değişkenleri tanımlı değilse bunu açık bir uyarı olarak yazdır ("exact-value scan skipped: FREYA_BANK_TEAM_KEY not set") ve `--require-env` ile FAIL'e çevir; SUBMISSION.md komutu `source env.sh` sonrası çalıştırılmasını söylesin.

### 3. [Düşük] Self-test başarısızlıkları PASS sayılıyor
- `trace_self_tests` yalnızca satırların biçimini ve en az bir vaka olmasını arıyor; `result=fail` veya hepsi `platform_error` olsa da PASS. Yarışma şartı "yaptığı testi ve sonucunu yaz" (README satır 91); dürüst kayıt uyumlu. Ama ekip için faydalı olur: toplamda `fail` veya `platform_error` varsa çıktı satırına `WARN` ekleyin (PASS kalsın). Ayrıca `--no-self-test` ile üretilmiş bir trace vaka satırı taşımadığı için zaten FAIL oluyor (doğru).

### 4. [Düşük] Kanıt bütünlüğü
- Girdi SHA-256 kayıtları biçim olarak kontrol ediliyor (≥2 girdi, 64 hex), ama gerçek dosyaların özetiyle karşılaştırılmıyor; dışa aktarımın bu koşuya ait olduğu yalnızca `workflow_id` ve adım sayısı eşleşmesiyle kanıtlanıyor (`updated_at` trace aralığında mı bakılmıyor). Yanlış PASS ihtimali düşük (başka koşunun dışa aktarımı aynı workflow kimliğini ve adım sayısını taşırsa geçer; aynı yuvada tekrar çalıştırıldığında olası). Öneri: dışa aktarımın `updated_at` değerinin trace `start_utc`–`end_utc` aralığında olmasını isteyin.

## Doğrulananlar

**README şartlarının kapsanması** (`build-the-builder-v2/README.md` satır 71–91):

| Şart | Kontrol |
|---|---|
| Başlangıç ve bitiş zamanı | `start_utc`/`end_utc` UTC, bitiş ≥ başlangıç |
| 30 dakikayı geçmeme (self-test dahil) | iki bağımsız ölçüm: `total_duration_seconds` (monotonik saat) ve zaman damgaları farkı, ikisi de < 1800 sn |
| Her model çağrısı (model, tek satır amaç) | `model_calls: N` toplamı ile ayrıntılı `model_call` satırı sayısı eşit; her satırda `model=`, `purpose=`, `duration_seconds=` |
| Freya'da yarattığı | `workflow_id`, `agent_id`, `published_version`, node/global/steps/tools sayıları, `steps = nodes + global_nodes` |
| Kendi ajanında yaptığı test ve sonucu | `self_test` vaka satırları + `self_test_summary` |
| Girdi izleri | `input:` satırları, `sha256=` |
| Elle adım yok | `--spec` ve `--single-step` koşuları `model_calls: none` yazdığı için model sayısı şartını sağlayamıyor ve FAIL oluyor; yani gerçek bir extraction koşusu zorunlu |
| Spec kanıtı | trace'in adını verdiği spec dosyası var ve `--spec` argümanıyla aynı |
| Dışa aktarım | JSON, `workflow` nesnesi, trace ile `workflow_id` ve adım sayısı uyumu |
| Anahtar sızıntısı yok | bulgu 2 |
| "Her final brief için bir trace" | slot başına bir trace/dışa aktarım çifti, SUBMISSION.md bunu ve form alanlarını (`team`, `repo`, `commit`, `run_command`) açıklıyor |

**Anahtar taraması (kendim denedim):** `fak_…` (Freya), `sk-ant-…` (Anthropic), `Authorization`/`x-api-key`/`x-team-key` başlık adları (JSON ve düz metin), `FREYA_BANK_TEAM_KEY=<16+>` yakalanıyor; gerçek dışa aktarım (`submission/brief-a.workflow.json`) taramadan temiz çıkıyor.

**Redaksiyon korunuyor:** `run_trace.py` değişikliği yalnızca monotonik `total_duration_seconds` satırı ekliyor ve bu satırı mevcut `add()` yolundan yazıyor; `_clean` (ortam değişkeni değerleri, `fak_`, `sk-ant-` maskeleme) ve `finish()` sırası aynı; `status` ve `end_utc` hâlâ yazılıyor, hata yolunda da (`finally`). `build.py`: `steps = nodes + global_nodes` eklenmiş (bağımsız sayılar korunmuş).

**Yanlış PASS riski:** küçük. Yukarıdaki dört şey dışında, eksik alan, çift sayım uyuşmazlığı, 30 dakika sınırı, geçersiz zaman damgası, spec/trace uyuşmazlığı gerçekten FAIL veriyor (testli).

## Kurallara uyum
Freya/model isteği yok, stdlib, `freya.py` değişmemiş. Redaksiyon kuralı korunmuş.

## Düzeltme sonrası
Bulgu 1 düzelince, gerçek bir canlı koşunun çıktısı olan trace + dışa aktarım + spec üçlüsüyle `submission_check.py` tamamen PASS vermeli; bunu bir kez onaylı canlı build sonunda deneyin (kontrolcü çevrimdışı, Freya'ya gitmiyor).

---

# Fix kontrolü (bulgu 1–4; rapor: tasks/T-008-report.md "Fix")

Kod değiştirmedim, Freya ve modele istek atmadım. `python3 -m unittest`: 201 test geçiyor. Kapsam: `tools/submission_check.py`, `tests/test_submission_check.py`, `builder/run_trace.py` ve `builder/build.py` trace satırları (F-043/044 workflow.py/prompts.py dahil değil).

## Karar: merge edilebilir
Dört bulgu da kapandı. Gerçek `submission/brief-a.workflow.json` ile yanlış FAIL kalmadı (aşağıda kendi çalıştırmam); eldeki `traces/brief-a.log` eski bir `--spec` koşusundan ve zaten uyumsuz, tam PASS yeni onaylı canlı koşuyu bekler.

## Kendi çalıştırmam
1. **Gerçek eski trace + gerçek dışa aktarım** (`traces/brief-a.log`, T-008 öncesi `--spec` koşusu): dışa aktarım maddeleri (`export_parses`, `export_workflow_id_matches`) ve `no_secrets` PASS; `agent_config`/`null` kaynaklı hiçbir FAIL yok. FAIL'ler yalnızca o izin hiç taşımadığı alanlar (`total_duration_seconds`, `model_call`, `steps`, self-test satırları, `sent_*`, spec yolu) ve `--spec` koşusu `model_calls: none` yazdığı için model şartı; yani doğru FAIL.
2. **Tam (sentetik tamamlanmış) iz + aynı gerçek dışa aktarım:** gerçek girdi SHA-256'ları, 2 model çağrısı, `nodes 20 / global 12 / steps 32 / tools 7` (dışa aktarımla birebir), `sent_agent_config: absent`, `sent_nulls: 0`, üç self-test satırı (biri `fail`, biri `platform_error`), `--spec` olarak canlı spec ve `--verify-inputs` ile çalıştırdım: **19/19 PASS**, 2 uyarı, çıkış kodu 0. Dışa aktarımdaki `agent_config` ve ~100 `null` artık FAIL vermiyor; `export_step_count_matches` 32 = 32.
3. **Not:** bu ikinci iz benim kurduğum bir şablon; gerçek tam PASS kanıtı için yeni bir canlı build'in çıktısı gerekiyor (rapor da böyle diyor).

## Bulgu durumu

| # | Bulgu | Durum |
|---|---|---|
| 1 | `agent_config`/`null` platformun eklediği alanlarda hep FAIL | **Kapandı.** `export_has_no_null` ve `export_omits_agent_config` kaldırıldı; yerine `sent_definition_clean`: trace'te `sent_agent_config: absent` ve `sent_nulls: 0` aranıyor. `build.py` bunları `tools` satırından sonra, `validate_workflow`/kaydetmeden **önce**, builder'ın gönderdiği tanım üzerinde sayıyor (`_count_nulls`, `_has_key`, satır 265–266). Dışa aktarım yalnızca ayrışma, kimlik, adım sayısı ve anahtar taraması için kontrol ediliyor. Testler platform biçimli (agent_config + null) bir dışa aktarımla PASS ve `present`/`null`/eksik satırla FAIL doğruluyor. |
| 2 | Takım anahtarı taraması zayıf | **Kapandı.** Denedim: `{"team_key": "abcdefghijklmnopqrst"}` artık yakalanıyor; `Bearer <uzun>` ve `?apikey=…`/`?token=…` sorgu anahtarları yakalanıyor; `{{token}}` şablonu ve zararsız metin ("The token count is 5…") ve normal URL (`?customer_id=c_123`) işaretlenmiyor. Ortam değişkeni tanımlı değilse `no_secrets` PASS ama açık `WARN: exact-value scan skipped: … not set`; `--require-env` ile FAIL (denedim: çıkış FAIL). Ortamdaki gerçek değer metinde varsa yakalanıyor (`value from FREYA_BANK_TEAM_KEY`). Kalan boşluk: 16 karakterden kısa, adsız (`team_short`) bir değer yalnızca ortam değişkeni tanımlıyken yakalanır; `SUBMISSION.md` komutu `source env.sh` ve `--require-env` ile çalıştırmayı söylediği için kabul. |
| 3 | Self-test başarısızlıkları sessiz PASS | **Kapandı.** `trace_self_tests` PASS kalıyor ama `WARN: self-test not passed: identity_failure_honesty=fail, third_party_close=platform_error` yazıyor; özet satırı uyarı sayısını veriyor. |
| 4 | Girdi özetleri dosyalarla karşılaştırılmıyor | **Kapandı.** `--verify-inputs` her `input:` satırındaki dosyayı yeniden özetleyip karşılaştırıyor (`inputs_match_files`: eşit PASS, değişmiş/yok FAIL; testli, benim çalıştırmamda 2 dosya eşit). `updated_at` aralığı kontrolü eklenmedi; istek yalnızca özet seçeneğiydi, kabul. |

## Redaksiyon ve trace
`run_trace.py` yalnızca monotonik `total_duration_seconds` satırı ekliyor ve `add()` yolundan yazıyor: sahte `FREYA_API_KEY=fak_…` ve `sk-ant-…` değerleri iz satırında `[REDACTED]` oluyor (denedim); `status`/`end_utc` hata yolunda da yazılıyor. `--print` izinde `sent_agent_config`/`sent_nulls` görünüyor (testli).

## Kurallara uyum
Model/Freya isteği yok, stdlib, `freya.py` değişmemiş, `docs/SUBMISSION.md` yeni komutu (`source env.sh` + `--verify-inputs --require-env`) ve WARN/`agent_config` açıklamasını içeriyor.

## Sonraki adım
İlk onaylı tam canlı build'den sonra `python3 tools/submission_check.py traces/<slot>.log submission/<slot>.workflow.json --spec traces/<slot>.spec.json --verify-inputs --require-env` komutunu `source env.sh` ile çalıştırın; bütün maddeler PASS olmalı (self-test başarısız olsa bile yalnızca WARN).
