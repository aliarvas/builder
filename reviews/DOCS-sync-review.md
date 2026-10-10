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
