# T-005f raporu: conversation tool politikası ve sentetik OpenAPI

**Geliştirici:** codex-dev · **Tarih:** 2026-10-10

## Sonuç

SELF-TEST denetiminin builder tarafındaki 1 ve 4 numaralı bulguları kapatıldı. Her conversation node artık gösterilebilecek her prompt alanında araç durumunu açıkça bildiriyor; sentetik spec de bellekte değiştirilen kit şeması yerine kendi OpenAPI fixture'ıyla render ediliyor.

Freya'ya istek gönderilmedi, `env.sh` okunmadı ve commit atılmadı. `builder/llm.py` ile `prompts.py` içindeki extraction prompt metinlerine dokunulmadı. Builder içine brief'e özgü değer eklenmedi.

## Değişiklikler

### İki yönlü conversation tool kuralı

- `builder/prompts.py` içine iki genel telefon-agent şablonu eklendi:
  - tools boşsa: `No tool call is allowed in this turn.`
  - tools doluysa: her `function.name` birebir yazılıyor; müşteri yanıtı adımın ilgili koşulunu karşıladığında ve gerekli girdiler bilindiğinde çağrılması söyleniyor.
- `builder/workflow.py` içindeki tek ortak uygulayıcı hem `task_message` hem varsa `loop_prompt` alanına bu kuralı ekliyor.
- Uygulayıcı spec workflow'daki normal ve global node'ların tamamına çalışıyor. Ortak `_conversation` yardımcısını atlayan tool'suz özel global conversation node'ları da böylece kapsanıyor.
- Eski tek-node `build_workflow` yolu da aynı uygulayıcıyı kullanıyor.
- İsimsiz bir conversation tool görülürse render sessizce eksik prompt üretmek yerine hata veriyor.

### Sentetik OpenAPI fixture

- `tests/fixtures/openapi-synthetic.json`, kit `build-the-builder-v2/tools/openapi.json` dosyasının kopyası olarak eklendi.
- Yalnız `close_call` şemasındaki enum sözleşmesi sentetik spec'e uyarlandı:
  - `outcome`: sentetik spec'teki bütün outcome değerleri;
  - `reason`: sentetik spec'teki boş olmayan bütün reason değerleri.
- `tests/test_multi_step.py` artık sentetik koşulda kit enum'unu bellekte genişletmiyor; fixture indeksine göre gerçek OpenAPI dosyasını okuyor.
- Ayrı test, sentetik outcome/reason enum'larının spec ile aynı kümeyi taşıdığını ve bu enum değişiklikleri dışında dosyanın kit OpenAPI ile aynı olduğunu doğruluyor.

### Test kapsamı ve prompt kataloğu

- Yeni unit test üç spec fixture'ını da render ediyor; `nodes` ve `global_nodes` içindeki bütün conversation node'larında:
  - tool yoksa no-tool cümlesini;
  - tool varsa her exact `function.name` ve ortak çağrı koşulu cümlesini;
  - varsa `loop_prompt` için aynı koşulları doğruluyor.
- `docs/PROMPTS.md`, `python3 -m builder.prompts` ile yeniden üretildi.
- İlk tam koşudaki fixture karşılaştırma sırası ve stale prompt belgesi hataları F-038 olarak `docs/UAT-FINDINGS.md` içine kaydedildi ve düzeltildi.

## Doğrulama

- `python3 -m unittest` — **132/132 geçti**.
- `python3 -m json.tool tests/fixtures/openapi-synthetic.json` — geçti.
- Prompt belge güncellik eşitliği — geçti.
- `git diff --check` — geçti.
- En yüksek conversation prompt tahmini:
  - Brief A fixture: **648** token;
  - Brief B fixture: **615** token;
  - sentetik fixture: **547** token.

Üçü de 1.500 token sınırının altında.
