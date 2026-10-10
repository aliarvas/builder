# T-005f review (conversation tool politikası, sentetik OpenAPI)

Rapor: tasks/T-005f-report.md; kaynak reviews/SELF-TEST-audit.md bulgu 1 ve 4. Kod düzenlemedim, Freya'ya istek atmadım. `python3 -m unittest`: 132 test geçiyor. Kapsam yalnızca T-005f; claude-dev'in extract.py ve Codex'in spec.py/offer_check.py işleri dahil değil.

## Karar: merge edilebilir
Kitin iki yönlü kuralı (`workflow-format.md:141-142`) A, B ve sentetik üretimlerde her conversation node için sağlanıyor. Sentetik OpenAPI yalnızca `close_call` enum'larında farklı. İki düşük bulgu (1, 2) bir sonraki işte kapatılabilir; ilk onaylı chat testi için engel değil.

## Doğrulama (kendi kontrolüm, testlerden bağımsız)
Üç fixture'ı (A, B ve sentetik, sentetik kendi OpenAPI dosyasıyla) üretip `nodes` ve `global_nodes` içindeki her `conversation` node'u taradım:

| Fixture | conversation node | Tools boş: "No tool call is allowed in this turn." | Tools dolu: her `function.name` birebir | İhlal |
|---|---|---|---|---|
| A | 7 | evet | `schedule_callback` (third_party), `verify_identity` (identity), `create_promise` (confirm_record) | 0 |
| B | 8 | evet | yukarıdakiler + `add_note` (özel yol) | 0 |
| Sentetik | 6 | evet | aynı | 0 |

- Tools dolu node'larda no-tool cümlesi yok (çelişki yok). Node tipi olarak yalnızca conversation, code, api_request, end_call var.
- Global node'lar: tarama `global_nodes`'u da içeriyor; B'de `special_human_transfer` global conversation node'u kapsandı (ihlal 0). Kod tipli global giriş adımları conversation değil, kural gerekmiyor.
- Uygulayıcı tek yerde (`_apply_conversation_tool_rules`, `workflow.py:157`), `build_spec_workflow` sonunda tüm node'lara ve `build_workflow`'un tek node'una çağrılıyor; isimsiz tool için hata veriyor (sessiz eksik prompt yok). Metinler `prompts.py` kataloğunda (`CONVERSATION_NO_TOOL_RULE`, `CONVERSATION_TOOL_RULE_TEMPLATE`) ve PROMPTS.md'de.
- `task_message` ve varsa `loop_prompt` ikisine de ekleniyor (kod `for field in ("task_message", "loop_prompt")`).

## Sentetik OpenAPI fixture
`tests/fixtures/openapi-synthetic.json` ile kit `openapi.json` arasındaki tam fark (özyinelemeli karşılaştırma):
- `close_call` `outcome.enum`: kit değerleri yerine sentetik spec'in 5 outcome'u (`settled, escalated, unfinished, unverified, unreached`);
- `close_call` `reason.enum`: eklenmiş (kitte yok), sentetik spec'in 4 reason'ı (`specialist, declined, attempts, delegate`).
Başka hiçbir yol, şema veya açıklama değişmemiş; spec'teki küme ile fixture enum kümesi birebir aynı. Rapor ile uyumlu, istenen koşul sağlanıyor ("yalnız close_call enumları").

## Prompt bütçesi
Adım başına en büyük tahmin: A identity 648, B identity 615, sentetik identity 547; negotiate 458/445/405, confirm_record 374/368/322. Hepsi 500–1.500 aralığında veya altında. Kural cümleleri adım başına yaklaşık 45 token ekliyor.

## Bulgular
1. **[Düşük] "Çağrı koşulu" genel bir cümle; adımın kendi koşulunu bağlamıyor.** Kural: "Call X only when the customer's response meets this step's stated condition ... do not call it otherwise." Kit "ne zaman çağrılacağını söyle" diyor. `third_party` ve `identity` prompt'larında araç için açık bir koşul cümlesi yok (yalnızca genel kural), yani cümle ayrıntı vermeden "stated condition" diye atıf yapıyor. Biçim olarak kit denetimini geçer; ama her tool için tek cümlelik gerçek koşul (ör. `schedule_callback`: "müşteri geri arama zamanı söylediğinde", `verify_identity`: "müşteri güvenlik sorusunun cevabını verince") spec'ten ya da tool açıklamasından üretilirse hem kit hem model davranışı daha iyi olur. Bir sonraki işte yapılabilir.
2. **[Düşük] Özel yol node'unda çelişkili ton.** B `special_product_dispute` görevi "Call the available tool once before claiming any action" diyor, hemen ardından eklenen genel kural "only when the customer's response meets this step's stated condition ... do not call it otherwise" diyor. Müşteri zaten ilgili şeyi söylediği için koşul sağlanıyor, ama model "koşul belli değil" diye çağrıyı erteleyebilir. Chat testinde B itiraz vakasında not aracının çağrılıp çağrılmadığına bakın; sorun çıkarsa özel yol şablonuna giren araç için kuralı "Call add_note now" biçiminde özelleştirin.
3. **[Bilgi] `loop_prompt` yolu fiilen test edilmiyor.** Hiçbir üretilen node `loop_prompt` taşımıyor; uygulayıcı bu alanı işliyor ama yeni test yalnızca "varsa" koşuluyla kontrol ediyor, yani bu dal bugün çalışmıyor. Kit kuralı karşılanıyor (alan yok); ileride `loop_prompt` eklenirse otomatik kapsanır. İsterseniz sentetik bir node ile tek birim testi ekleyin.
4. **[Bilgi] Sentetik fixture'a eklenen `reason.enum` kitte yok.** Gerçek (hidden) tool dosyasında `reason` serbest string. Bu fixture'la extraction/renderer kontrolleri gerçekte olmayan bir kısıtla geçiyor olabilir; gizli dosyada enum olmadığı durumu ayrıca A ve B fixture'ları kapsıyor, bu yüzden sorun değil.

## Hardcode ve kurallar
Kural metinleri genel (araç adı yer tutucu); brief değeri yok. Freya isteği yok, stdlib. Eski tek-node yol aynı uygulayıcıyı kullanıyor (kod `close_call`/`transfer_to_agent` için aynı kural; legacy, `--single-step`).

## Kapanış
SELF-TEST-audit bulgu 1 (iki yönlü kapı) ve bulgu 4'ün builder tarafı (sentetik OpenAPI) kapandı. SELF-TEST dokümanındaki kontrol listesi de aynı iki yönlü kapıyı ve tool adı kontrolünü içermeli (bulgu 1'in belge kısmı) ve sentetik `--print` komutu `tests/fixtures/openapi-synthetic.json` dosyasını kullanmalı; bu belge işi review kapsamı dışında, CTO'ya not.
