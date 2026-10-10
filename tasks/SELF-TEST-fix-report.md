# SELF-TEST düzeltme raporu

`docs/SELF-TEST.md`, `reviews/SELF-TEST-audit.md` içindeki 12 bulgunun tamamına göre güncellendi. Belgenin dokuz adımlı yapısı, başlıkları ve Türkçe operasyon dili korundu; yalnız yanlış veya eksik kapılar değiştirildi.

## Uygulanan düzeltmeler

1. Conversation prompt kontrolü iki yönlü hale getirildi: tool yoksa açık yasak; tool varsa exact function adı ve çağrı koşulu.
2. `--print` ile gerçekten offline olan `--print --spec` ayrıldı; `ANTHROPIC_API_KEY` ve model çağrısı açıklandı.
3. Extraction tekrar koşusu, `compare_spec.py`, anlam kapıları, çağrı/repair/warning/unmapped sayıları ve 5 dakikalık extraction hedefi eklendi.
4. Sentetik spec'in yalnız `tests/fixtures/openapi-synthetic.json` ile eşleştirilmesi yazıldı.
5. Yerel A+B komutu ile final run contract belirsizliği ayrıldı ve `[TO-CONFIRM]` olarak bırakıldı.
6. Dört aşamada hang-up ve 502/503/504 sonrası call-record/ledger uzlaştırması eklendi.
7. En az üç farklı `now` için güncellenmiş `expected` alanlarıyla otomatik ledger doğrulaması istendi.
8. PUB-11, PUB-12 ve PUB-13 için ayrı 3/3 çok-ürün kapısı eklendi.
9. Workspace sınırının 10/200 kaynak çatışması belirtildi; update-in-place kuralı sınırdan bağımsızlaştırıldı.
10. Trace alanları tam listeye çıkarıldı ve güncel `submission_check.py --verify-inputs --require-env` komutu eklendi.
11. Doğrulanmamış “ilk 10” ifadesi “üst sıralardaki takımlar” olarak düzeltildi; Adım 8 başlığı da aynı şekilde güncellendi.
12. Hardcode kontrolü AST tabanlı leak testi + hedefli literal karşılaştırması + gerekçeli framework allowlist olarak tarif edildi.

Ek olarak teslim provası form alanlarıyla tamamlandı; builder'ın güncel spec-tabanlı, sıralı ve 6 dakikalık self-test davranışı belgeye işlendi.

## Uygulanmayan bulgu

Yok. On iki bulgunun tamamı belge kapsamındaydı ve uygulandı.

## Doğrulama

- `docs/SELF-TEST.md` ile güncel `builder/selftest.py`, `builder/build.py`, `tools/submission_check.py`, `docs/EVALUATION-AND-TESTING.md` ve kit README davranışları karşılaştırıldı.
- Eski “ilk 10”, kesin “workspace 200”, gelecek zamanlı T-006 şartı ve manuel-only farklı-`now` ifadelerinin kalmadığı tarandı.
- `git diff --check -- docs/SELF-TEST.md tasks/SELF-TEST-fix-report.md` temiz geçti.
- Kod değiştirilmedi; Freya/model isteği, commit ve `env.sh` erişimi yapılmadı.

## Fix

`reviews/SELF-TEST-fix-review.md` içindeki A–E bulguları uygulandı:

- Adım 1'e brief yolu, OpenAPI yolu ve benzersiz `--slot` içeren, doğrudan çalıştırılabilir Brief A, A+B ve sentetik spec komutları eklendi. Workflow stdout hedefleri ile `traces/<slot>.print.log` konumları açıklandı.
- `compare_spec.py` kapsamı gerçek davranışına indirildi: araç davranış değerlerini karşılaştırır, `coverage.unmapped` öğelerini raporlar ve farkta 1 döner; wording/provenance karşılaştırmaz. Override etkisinin değişen davranış değerinden görüldüğü, provenance ve `overrides` alanlarının ayrıca okunması gerektiği yazıldı.
- Resmi bayraksız koşu ile geliştirme provalarındaki `--slot` kullanımı ayrıldı. Bayraksız slotun brief stem'inden, çoklu briefte stem'lerin `+` ile birleşmesinden türediği belirtildi.
- Manuel chat akışı pratik oturumu oluşturma, dönen `variables`/`customer_id` değerlerini kullanma, `callId`'yi sürdürme, chat'i bitirme ve ledger'da `close_call` sayısını doğrulama adımlarıyla yapılabilir hale getirildi. 5xx sonrası call kaydı ve ledger uzlaştırması aynı akışa bağlandı.
- `--rerun-if-slow N` ifadesi “en fazla N yeniden koşu; her yeniden koşudan önce 5 dakika bekleme” olarak netleştirildi ve builder'ın 30 dakikalık bütçesinin dışında, yalnız geliştirme testinde kullanılması gerektiği yazıldı.

Kod değiştirilmedi; Freya/model isteği, commit ve `env.sh` erişimi yapılmadı.
