# DOCS-sync review (ARCHITECTURE, FREYA-INTEGRATION, EVALUATION-AND-TESTING, DEFINITION-OF-DONE)

Rapor: tasks/DOCS-sync-report.md. Kod düzenlemedim, Freya'ya ve modele istek atmadım. Yöntem: dört belgedeki somut iddiaları kodla, üretilmiş bir Brief A workflow'uyla (`tests/fixtures/spec-brief-a.json`), `traces/` içindeki gerçek izlerle, `docs/UAT-FINDINGS.md` ve `git ls-files` ile karşılaştırdım. `python3 -m unittest` şu an 234 test, hepsi geçiyor.

## Karar: düzeltme gerekli (küçük, yalnızca belge)
Belgelerin büyük çoğunluğu koda ve izlere uyuyor ve rapor yöntemi sağlam. Ama kanıtsız bir "doğrulandı" iddiası, "commit edilmiş" diyen yanlış bir ifade ve birkaç eskimiş/çelişkili cümle var. Hepsi tek tur belge düzeltmesiyle kapanır; kod değişikliği gerekmez.

## Yanlış ya da kanıtsız iddialar (düzeltilmeli)

1. **[Yüksek] ARCHITECTURE "Core design idea `[VERIFIED by chat tests]`": "The baseline's failures F-001..F-004 no longer appear."** UAT kayıtlarına göre yalnızca F-002 canlı chat'te yeniden test edildi (PUB-03, sürüm 5). F-001 ("not yet retested in chat", PUB-02), F-003 ("Retest pending (PUB-07)") ve F-004 ("not yet retested in chat", PUB-09) canlıda yeniden denenmedi; PUB-07 sürüm 8'de başka bulgular çıktı (F-025..F-031), düzeltmeleri çevrimdışı. Cümle "F-002 and the PUB-01 ledger check passed in chat; F-001, F-003 and F-004 are fixed in code and still to be retested live" gibi yazılmalı. `[VERIFIED]` etiketi yalnızca iki chat sonucuna bağlanmalı.
2. **[Orta] FREYA-INTEGRATION "Vertical slice": "The latest committed live run is `traces/brief-a.log` … with `submission/brief-a.workflow.json`."** `git ls-files traces submission` boş: iki klasör takipte değil (untracked), yani "committed" yanlış; bu dosyalara yapılan atıflar (DEFINITION-OF-DONE kanıtları: `traces/brief-a.log`, `traces/f040-*.print.log`, `submission/brief-a.workflow.json`) yeni bir klonda bulunmaz. Ya bu kanıt dosyaları commit edilmeli ya da cümle "latest local live run (not committed)" demeli.
3. **[Orta] FREYA-INTEGRATION: "No other module imports `freya`."** `freya_chat.py` `from . import freya` ile kit istemcisinden `URL` ve `HEADERS`'ı alıyor (ARCHITECTURE kuralı bunu doğru söylüyor: "only `build.py` and `freya_chat.py`"). Cümle "…besides `build.py` and `freya_chat.py`" olmalı.
4. **[Düşük] ARCHITECTURE "Lifecycle tool: the closing chain records exactly one close."** Aynı belge ve FREYA-INTEGRATION `close_call`'ın başarısızlıkta en fazla iki kez gönderildiğini söylüyor. "At most one successful close; a failed attempt is retried once" daha doğru.
5. **[Düşük] FREYA-INTEGRATION, yeniden denemeler:** "Write tools (`create_promise`, closing and special-path tools) get `maxRetries: 0`." Üretilen workflow'da `verify_identity` ve `schedule_callback` da `maxRetries 0` (kendim listeledim); `get_account` 1. Liste eksik, yanlış değil; "all tools except `get_account`" demek yeterli.
6. **[Düşük] Eskimiş sayılar/dosya listeleri:** DEFINITION-OF-DONE "225 tests OK" (şu an 234). `builder/spoken.py` (F-047/048, çalışma ağacında; `extract.py` ve `workflow.py` içe aktarıyor) ARCHITECTURE bileşen tablosunda ve boru hattında yok; `tests/test_spoken_text.py` EVALUATION tablosunda yok. Test sayısı sabit yazılmasın (yalnızca "all pass") ya da commit öncesi güncellensin.

## Doğrulanan iddialar (örnekler)

| Belge | İddia | Kanıt |
|---|---|---|
| ARCH | Çıkış kodları: girdi/OpenAPI/spec hatası 2, diğer 1; ikisi `traces/<slot>.failed.log` yazar | `build.py` `except` blokları |
| ARCH | İskelet: `opening_reask`, `opening_unclear`, `offer_setup`, `confirmation_progress`, `closing`→`closing_say`→`close_attempt`→`close_record`→`end_call`, `close_turn_limit`, `close_special_tool_failed`, global özel yollar, `close_call_on_hangup` (`alwaysRunsAt: end_of_call`, hook URL'yi boşaltır) | üretilmiş Brief A workflow'u |
| ARCH | `get_account` pre-action `maxRetries 1`, bekleme cümlesi söylüyor | `account` düğümü: `api_request`, `tts`, `passthrough`, `get_account` pre-action `maxRetries 1` |
| ARCH | Post-hook `data.ok = False` yapar (HTTP hatası, hata durumu, `error` alanı, eksik `ok`, dict olmayan veri), `what_to_do_next` yazar, hiç fırlatmaz | `tools_from_openapi.py` `_post_process_code` (`try/except: pass`) |
| ARCH | Model `claude-sonnet-5-5`, sıcaklık gönderilmiyor, `max_tokens 16000`, zaman aşımı 300 sn, yeniden deneme 408/429/5xx/529 ve ağ hatası (tek) | `llm.py` |
| ARCH | Bağımlılık kuralları: `spec.py` builder'dan hiçbir şey içe aktarmıyor; `workflow/offer_check/extract/tools_from_openapi` `freya` içe aktarmıyor; yalnızca stdlib | importlar |
| ARCH | `MAX_REPAIR_ROUNDS = 2`, `spec.failed.json`, kapsama + tek takip, `coverage_rejected`/`coverage_unmapped`, `rule_tiers`, `rule_placement`, `prompt_estimate` izleri | `extract.py`, `build.py` |
| ARCH | `.freya-agents.json` git'te yok sayılıyor | `.gitignore` |
| ARCH | Bütçe: hedef 1.200, sınır 1.500, aşamalar, karakter/4 tahmini, e4ed265'te `SpecError`, çalışma ağacındaki değişiklik `budget_exceeded_but_shipped` | `workflow.py`; T-009b'yi `[TO-CONFIRM]` olarak doğru işaretliyor, T-009b incelemem yeni davranışı doğruladı |
| FREYA | Kuru çalıştırma `--validate`'te ve her kayıttan önce; 404'te bayat slot düşer; yayın okuyup doğrular (`_ensure_published_version`); dışa aktarım self-test'ten önce; anahtarsız kayıt istek atmadan durur; builder takım anahtarını kullanmıyor | `build.py`, `slots.py`, `freya.py` |
| FREYA | `close_call_on_hangup` URL'yi zincir göndermişse boşaltır | hook kodu |
| FREYA | Platform davranışı notları (F-021, F-023, F-031, F-043, dışa aktarımın kendi `agent_config`/`null` değerleri) | UAT kayıtları ve gerçek `submission/brief-a.workflow.json` (agent_config ve null var) |
| EVAL | L2 self-test üç vakası, `MAX_CLOSE_ATTEMPTS = 2`, `MAX_NODE_TURNS = 6`, 6 dakika, 5xx'te kayıt okuma, çağrı bitince gönderme durur | `selftest.py` |
| EVAL | L4 komutu ve kontrolleri; WARN davranışı | `tools/submission_check.py` |
| EVAL | Sonuç günlüğü satırları (6/10 taban çizgisi; v5 PUB-03, v8, v10 PUB-01); "tam puanlı koşu yok" | UAT kayıtları |
| DoD | Çıkarma süreleri "128 ila 222 sn" | `traces/f040-*.print.log`: 128,6 / 168,5 / 184,8 / 221,7 sn (sonraki f041 koşuları 91–131 sn) |
| DoD | changed-a ve raw-a `status: ok`, `unmapped_items=0`; memo kazanır | f040-changed/raw: 0 eşlenmemiş; f041-raw.spec.json: erken bant 10 iş günü, kimlik sırası `phone_last4, date_of_birth` |
| DoD | Kutular dürüst: uçtan uca canlı koşu, zamanlı 30 dk koşusu, 3.10 temiz klon, üç güvenlik/dürüstlük maddesi, pratik skorları ve tüm teslim maddeleri açık bırakılmış | belge + raporlar |

## Notlar (düzeltme gerekmez ama belgelerde görünsün)
- DoD "Works on a brief with a different layout and a different tool API `[x]`" kanıtı çıkarma + render (`--print` `status: ok`), canlı ajan koşusu değil. İşaret kalabilir; kanıt satırı "extraction and render" demeli, "works" ifadesi canlı çalışmayı çağrıştırıyor.
- f041-raw koşusu 3 eşlenmemiş madde bıraktı (f040'ta 0); DoD f040'a atıf yapıyor ve doğru, ama "en son tekrarda 3 madde" bilgisi eklenebilir.
- ARCH'taki `[VERIFIED: code, commit e4ed265]` etiketleri çalışma ağacında değişmiş dosyalar (`build.py`, `workflow.py`, `extract.py`, `prompts.py`) için commit sonrası yeniden doğrulanmalı; belge bunu T-009b satırında zaten `[TO-CONFIRM]` diye işaretliyor.

## Kurallara uyum
Yalnızca dört belge değişmiş (kod, test ve fixture'a dokunulmamış); Freya/model isteği yok; belgeler anahtar içermiyor.

---

# Fix kontrolü (rapor: tasks/DOCS-sync-report.md "Fix", bölüm 2 ve F-050 sonrası güncellemeler)

Kod düzenlemedim, Freya ve modele istek atmadım. `python3 -m unittest`: 245 test geçiyor (belgedeki sayı da 245).

## Karar: düzeltme gerekli (küçük)
Önceki incelemenin altı maddesi doğru kapatılmış. Ama belgeler "resmî sürüm 11 koşusu" kanıtına dayanıyor ve o iz dosyası sonradan yeni bir resmî koşuyla (sürüm 12) **üzerine yazılmış**; belgelerdeki sayılar ve atıf eski koşuya ait, güncel `traces/brief-a.log` ile uyuşmuyor. Aşağıda ayrıntı. Tek turluk belge güncellemesi yeterli.

## Önceki maddeler: kapandı
| # | Madde | Durum |
|---|---|---|
| 1 | "F-001..F-004 no longer appear" | **Kapandı.** ARCHITECTURE artık "Evidence is two chat results only": PUB-03 (v5, F-002 yeniden test) ve PUB-01 (v10) defter geçişi; F-001, F-003, F-004 "fixed in code and still to be retested live"; PUB-07 v11 F-050 yüzünden başarısız. |
| 2 | "committed live run" | **Kapandı.** FREYA-INTEGRATION ve DoD: `traces/` ve `submission/` kanıtları yerel ve **not committed yet** (`git ls-files traces submission` hâlâ boş, iddia doğru). |
| 3 | "No other module imports `freya`" | **Kapandı.** "Besides `build.py` and `freya_chat.py` …". |
| 4 | "exactly one close" | **Kapandı.** "At most one successful close; a failed `close_call` is retried once." |
| 5 | `maxRetries` listesi | **Kapandı.** "Every tool except `get_account` has `maxRetries: 0` (write tools and also `verify_identity`, `schedule_callback`)". |
| 6 | Eskimiş sayılar/dosya listeleri | **Kapandı.** `spoken.py` boru hattında (extract ve render satırları) ve bileşen tablosunda; `test_spoken_text.py` ve güncel `test_selftest.py`/`test_spoken_output.py` satırları EVALUATION tablosunda; test sayısı 245 (tarihli, "re-count before each commit" notu). |
| Not | DoD "works" ifadesi | **Kapandı.** "Extraction and rendering work … (not yet a live agent run)"; `f041-raw` 3 eşlenmemiş madde bilgisi eklenmiş. |
| Not | Commit etiketleri | **Kapandı.** Etiketler d5f6af1 (güncel HEAD), bütçe satırından `[TO-CONFIRM]` kalkmış (davranış commit'te). |

F-050 sonrası eklenenler de koda uyuyor: `account` adımı sessiz (`F-050`), kimlik adımı bekleme cümlesini söylüyor, `identity_check` iskelette, platform notlarında 502 geri alma davranışı, introduction yalnızca açılışta (F-048), `spoken_fallback` uyarısı (F-047); önceki incelemede bunları üretilmiş workflow'larda doğrulamıştım.

## Kalan sorun: sürüm 11 kanıtı artık mevcut dosyada yok
- Belgeler "official version 11 run, `traces/brief-a.log`, 2026-10-10 20:21 UTC, 183 s (extraction 103 s, self-test ~75 s), self-test 0/3 (F-045/F-046)" diyor (DoD maddeleri 1–3, ARCHITECTURE "Time", FREYA-INTEGRATION "Vertical slice", ARCHITECTURE "official run version 11").
- Mevcut `traces/brief-a.log` başka bir koşu: **20:39 UTC başlangıç, yayımlanan sürüm 12, toplam 193,2 sn** (çıkarma 103,5 sn, 6 model çağrısı), self-test `identity_attempt` **pass**, `identity_failure_honesty` **pass**, `third_party_close` **platform_error** ("close step entered but no close_call event visible in the call record"), `status: ok`, 24 düğüm + 9 global = 33 adım, `sent_agent_config: absent`, `sent_nulls: 0`. Yani DoD'daki "self-test 0/3" ve "183 s" bu dosyayı doğrulamıyor; kanıt gösterilen yol, anlatılan koşuyu taşımıyor.
- Bu yeni koşu belgelerde hiç yok ve daha güçlü kanıt: kendim `tools/submission_check.py traces/brief-a.log submission/brief-a.workflow.json --spec traces/brief-a.spec.json --verify-inputs` çalıştırdım → **SUMMARY: PASS (19/19), 2 uyarı** (üçüncü vakanın `platform_error`'ı ve ortam değişkeni taramasının atlanması). Bu, DoD'daki gönderim kapısı için ilk gerçek tam PASS.
- **Düzeltme:** (a) DoD maddeleri 1–3, ARCHITECTURE "Time" ve FREYA-INTEGRATION "Vertical slice" sayılarını/atıfı güncel koşuya (sürüm 12, 193 s, self-test 2 pass + 1 platform_error, resmî komut) çevir; (b) sürüm 11 sonuçlarını (0/3, F-045/F-046) yalnızca EVALUATION sonuç günlüğü satırında tarihli tarihsel kayıt olarak bırak ve o satırın artık hangi dosyada olmadığını yaz ("trace overwritten by the next run"); (c) gönderim kapısı olarak `submission_check` tam PASS'ını (19/19, 2 uyarı) DoD gönderim maddesine kanıt olarak ekle; (d) `third_party_close` `platform_error` nedeninin (motorun `pre_actions` ile çalıştırdığı `close_call` için `function_call_start` olayı kayıtta görünmüyor) EVALUATION L2 bölümüne eklenmesi.
- İz dosyalarının üzerine yazılmasını önlemek için her resmî koşunun `--slot` ile ayrı bir ad kullanması (örn. `brief-a-run2`) ya da kanıt iz dosyasının koşudan hemen sonra kopyalanması yararlı olur; DoD'un dayandığı dosya sonraki koşuyla değişiyor.

## Kurallara uyum
Yalnızca belgeler, `selftest.py` ve testi değişmiş; belgeler anahtar içermiyor; Freya/model isteği yok.

---

# Fix 2 kontrolü (rapor: tasks/DOCS-sync-report.md "Fix 2"; sürüm 12 kanıtı ve F-051)

Kod düzenlemedim, Freya ve modele istek atmadım. `python3 -m unittest`: 255 test geçiyor (claude-dev'in F-051 çalışması dahil değil). Bu tur yalnızca belgeler değişmiş.

## Karar: merge edilebilir
Önceki turda istediğim dört düzeltme (a–d) ve iz dosyası uyarısı doğru yapılmış; sayılar güncel `traces/brief-a.log` ile birebir uyuşuyor. Kalan tek nokta bilgi düzeyinde.

## Doğrulama
| Madde | Durum | Kanıt |
|---|---|---|
| (a) Sürüm 11 yerine güncel koşu | **Tamam** | `traces/brief-a.log`: başlangıç 2026-10-10 20:39 UTC, yayımlanan sürüm 12, `total_duration_seconds: 193.161`, `status: ok`; çıkarma 103,5 sn, 6 model çağrısı, `unmapped_items=0`; 24 düğüm + 9 global = 33 adım; self-test ≈ 84 sn (24,6 + 38,8 + 20,7). DoD maddeleri 1–3, ARCHITECTURE "Time" (193 s, 103,5 s, ~84 s) ve boru hattı etiketi, FREYA-INTEGRATION "Vertical slice" artık bu sayılar. `negotiate ~1586 -> ~1208` izdeki `budget:` satırıyla aynı. |
| (b) Sürüm 11 yalnızca tarihçe | **Tamam** | EVALUATION sonuç günlüğü: "version 11 (trace overwritten by the 20:39 run)", 0/3 ve F-045..F-048 nedenleri ayrı satırda; DoD maddesi o satıra işaret ediyor. |
| (c) Gönderim kapısı kanıtı | **Tamam, doğru dürüstlükte** | DoD gönderim maddesi: sürüm 12 provası `SUMMARY: PASS (19/19, 2 warning(s))` (bu, benim `--require-env` olmadan çalıştırmam), kutu hidden brief'ler ve `--require-env` için açık bırakılmış. |
| (d) `platform_error` nedeni | **Tamam** | EVALUATION L2: motor `close_call`'ı `close_record` `pre_action`'ı olarak çalıştırıyor ve olay yazmıyor; self-test deneme sayamaz, yalnızca ledger kanıtlar; `[TO-CONFIRM]` başka olayın (`function_call_complete`, `route_evaluated`) bunu taşıyıp taşımadığı. |
| İz dosyalarının üzerine yazılması | **Tamam** | EVALUATION "Evidence kept per run", DoD girişi ve FREYA-INTEGRATION: `traces/<slot>.log` sonraki koşuyla üzerine yazılır; kanıt koşusundan hemen sonra kopyala ya da yeni `--slot` kullan. |
| F-051 | **Doğru ve kanıtlı** | UAT'ta F-051 var (PUB-07 v12, yalnızca tarih cevabı → `offer_amount` boş → `check_offer` çalışmadı, model dahili adım çağrısını yazdırıp sınır uydurdu); EVALUATION sonuç günlüğü satırı ve ARCHITECTURE kanıt cümlesi aynı; `open` olarak işaretli ve "F-050 fix held" notu UAT ile uyumlu. |
| Türkçe dolgu gözlemi | **Doğru** | UAT ("filler appeared once more during a slow turn") ve kayıt dosyasında (`Bir saniye lütfen.` metni var, kendim aradım). FREYA-INTEGRATION'daki `[TO-CONFIRM]` bu gözlemle değiştirilmiş. |
| Test sayısı | **Kabul** | Belgelerde 245, rapor bunun son commit'in sayısı olduğunu ve F-051 işi commit edilince yeniden sayılacağını söylüyor; şu an 255 çalışıyor (F-051'in yeni testleri). Commit sonrası güncellenmeli. |

## Bilgi notları
- DoD yalnızca iki koşuya atıf yapıyor (güncel sürüm 12 ve tarihsel 11); iz dosyası kopyalanmadığı sürece bu atıf bir sonraki koşuda yine bozulur. Önerilen kopyalama/`--slot` uyarısı yazılı, uygulanması CTO'nun komut disiplinine bağlı.
- ARCHITECTURE `[VERIFIED: code, commit d5f6af1; official run version 12]` etiketi, F-051 çalışması commit edilene kadar doğru; commit sonrası etiketi yenileyin.

## Kurallara uyum
Belgeler anahtar içermiyor; yalnızca belge değişmiş; Freya/model isteği yok.
