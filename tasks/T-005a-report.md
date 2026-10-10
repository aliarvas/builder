# T-005a raporu: PUB-03 chat düzeltmeleri (F-019..F-022)

**Geliştirici:** claude-dev · **Tarih:** 2026-10-10

## Özet

F-019..F-022'nin dördü de koda yansıdı. `python3 -m unittest` 60 testin hepsini geçiyor (öncesi 50) ve `--print --spec tests/fixtures/spec-brief-a.json` çalışıyor. Hiçbiri Freya'da denenmedi; işe yarayıp yaramadıklarını ancak bir sonraki onaylı chat testi gösterir. Freya'ya istek yok, commit yok, `env.sh` okunmadı.

Değişen dosyalar: `builder/spec.py`, `builder/prompts.py`, `builder/workflow.py`, `tests/test_multi_step.py`, `tests/fixtures/spec-*.json` (üçü de), `docs/PROMPTS.md` (yeniden üretildi), `docs/UAT-FINDINGS.md`.

## Madde başına değişiklik

### F-019: Açılışta isim yok

Spec'e `opening.address_with` alanı eklendi (örn. `["title","last_name"]`). Açılış prompt'u bu alandan `{{title}} {{last_name}}` yer tutucularını üretiyor; kodda değişken adı yazılmıyor. Spec bu alanı doğruluyor: boş olamaz, her öğe geçerli bir değişken adı olmalı.

### F-020: Yanlış cevaptan sonra "thank you" deyip devam etme

- Kimlik şablonuna (`IDENTITY_TASK_TEMPLATE`) dört sonuç için genel kurallar girdi:
  - **Cevap doğru:** kısaca onayla, sıradaki soruya geç.
  - **Cevap yanlış:** "eşleşmedi" de, teşekkür etme, aynı soruyu tekrar sor. Bu soru doğrulanmadan sıradakine geçme.
  - **Araç işlemi yapmadı:** aynı cevabı tekrar iste; yanlış cevap sayılmaz.
  - **Hak kalmadı:** spec'teki cümleyi söyle, başka soru sorma, hesap bilgisi verme.
- Konuşmadaki cevabı (tarih, rakam) araç formatına ajan kendisi çeviriyor. Format bilgisi artık "kendin çevireceğin araç formatı" olarak yazılıyor, müşteriden istenen bir şey gibi okunmuyor.
- Brief'e özgü cümleler spec'ten geliyor; üç fixture'a da eklendi:
  - `answer_verified_field`: o cevabın sonucunu taşıyan alan
  - `failed_answer_instruction`: ipucu kuralı
  - `exhausted_say`: hak bitince söylenecek cümle

### F-021: Araç sonucundan sonra yönlendirme gecikiyor

Bkz. aşağıdaki "F-021 tasarım seçimi".

### F-022: Kapanış neden bittiğini bilmiyor

Outcome'u artık model seçmiyor:

- Çağrıyı bitiren her yol, nedeni `close_state` olarak kaydeden küçük bir kod adımından geçiyor. Örnekler: `close_identity_failed`, `close_promise_recorded`, `close_promise_failed`, `close_third_party_<değer>`, `close_special_<id>`, `close_turn_limit`. Tur sınırı (`max_turn_transition`) da bu yoldan geçiyor.
- `closing` kod adımı outcome, reason ve kapanış cümlesini spec tablosundan seçiyor. Tablodaki her satıra iki alan eklendi:
  - `on`: satırın kapsadığı bitiş durumları
  - `say`: kapanış cümlesi
- Özel yollar, kendi outcome/reason değerlerini kullanıyor. Eşlenmemiş bir durumda daha önce kaydedilmiş bir söz varsa `promise_recorded` satırı, o da yoksa `default` satırı seçiliyor.
- Sıra:
  1. `closing_say` cümleyi sabit satır olarak söylüyor.
  2. `close_attempt` deneme sayacını artırıyor.
  3. `close_record` (api_request) `close_call`'ı engine tarafında, sabitlenmiş `{{close_outcome}}` / `{{close_reason}}` değerleriyle çalıştırıyor.
  4. Çağrı `end_call` ile bitiyor.
- Retry sınırlı: `close_call` en fazla 2 kez çağrılıyor; ikisi de başarısızsa çağrı başarı iddia edilmeden bitiyor. T-004-fix2'deki dürüst başarısızlık davranışı korundu.
- Hiçbir sohbet adımında artık `close_call` yok. `end_call`'a yalnızca `close_record` gidiyor.
- Build şu durumlarda açık bir hatayla duruyor:
  - bir bitiş durumunun tabloda karşılığı yoksa veya bilinmeyen bir durum yazılmışsa (`spec.py`),
  - outcome değeri `close_call` enum'unda yoksa (`workflow.py`).
- Spec'te yeni `closing` bölümü var (`outcome_field`, `reason_field`); alan adları kodda yazılı değil.
- Trace artık engine'in çalıştırdığı araçları da gösteriyor (`get_account (engine)`, `close_call (engine)`).

### Testler

Eklenen testler şunları doğruluyor:

- `end_call`'a kapanış yolundan geçmeden ulaşılamıyor.
- Her bitiş durumu, üç fixture'da da doğru outcome'u veriyor.
- Kod adımları derleniyor, `{{`/`}}` içermiyor ve eksik değişkende hata vermiyor.
- Açılış prompt'u adres yer tutucularını içeriyor.
- Kimlik prompt'u yanlış cevap ve hak bitme kurallarını içeriyor.
- Hiçbir sohbet adımında kendine dönen `always` geçişi yok.
- Adım başına prompt, üç fixture'da da 1.500 token altında (en büyüğü Brief A identity, yaklaşık 481).

Sızıntı testi yeni fixture alanlarını da tarıyor.

## F-021 tasarım seçimi ve neden

İki katman seçtim:

1. **Sohbet adımlarındaki kendine dönen `always` geçişini kaldırdım.** Log'da identity adımı her turda kendine yeniden giriyordu (`node_enter identity from identity`). Bu yüzden araç sonucu geldiğinde o girişte "önceki asistan mesajı" kalmıyor gibi görünüyor. Kit dokümanına göre hiçbir geçiş eşleşmezse engine zaten adımda kalıyor (`workflow-format.md`, "Order of evaluation"), yani bu geçişe gerek yok. Bu değişiklik, adım yeniden girişinde `on_enter`'ın tekrar çalışmasını da (rereview N7) azaltabilir.
2. **Garanti olmadığı için yedek:** identity prompt'u hak bitince doğru cümleyi kendisi söylüyor ve soru sormayı bırakıyor. Yönlendirme bir tur gecikse de müşteri yanlış bir şey duymuyor.

Önerilen alternatif olan "araçtan sonra passthrough kod adımı"nı seçmedim. O adıma giden yönlendirme de aynı şekilde bastırılırdı, yani sorunu çözmezdi.

## TO-CONFIRM (sonraki onaylı chat testi)

1. Self-loop'u kaldırınca "Suppressed: Missing prior assistant message" ortadan kalkıyor mu, yani yönlendirme aynı turda oluyor mu? Voice'ta da aynı davranış var mı?
2. Passthrough kod adımındaki sabit cümle (`on_enter` tts `{{closing_say}}`) chat'te gerçekten söyleniyor mu, ve transcript'te `close_call`'dan önce mi görünüyor? Brief A kural 47 vedanın `close_call`'dan önce olmasını istiyor. Chat testinde ilk bakılması gereken şey bu.
3. `close_reason` hiç set edilmemişse (`promise`, `paid`) `reason` alanı istekten düşüyor mu (kit dokümanına göre düşmeli), ve banka bunu kabul ediyor mu?
4. Node seviyesindeki `response_mapping` (`data.ok` → `close_call_ok`) `close_record` adımında doluyor mu, ve post-hook pre_actions'ta da çalışıyor mu?

## Açık sorular

1. Spec formatı değişti: outcome satırlarına `say`/`on`, yeni `closing` bölümü, yeni identity alanları ve `address_with` geldi. T-006 extractor'ı bunları üretmek zorunda.
2. Brief'in tanımlamadığı bitiş durumlarının (`turn_limit`, `account_failed`) Brief A fixture'ında `no_promise/service_error`'a, `default` durumunun da `no_promise/refused`'a eşlenmesi benim seçimim. Doğru değerleri brief'ten çıkarmak extractor'ın işi.
3. Kapsam dışı kalanlar:
   - Kimliği reddetme (kural 15, `not_verified/declined`) hâlâ ayrı bir yol değil.
   - Geri arama başarısız olursa çağrı tekrar denemeden kapanıyor (eskiden de öyleydi).
4. Sızıntı testi artık kit'in sabit çağrı değişkeni adlarına (`title`, `last_name`, …) ve iskeletin bitiş-durumu adlarına (`identity_failed`, `default`, …) izin veriyor. Kit bu çağrı değişkenlerinin hep var olduğunu söylüyor (`STARTER-KIT-FACTS.md`), yani bunlar brief verisi değil. Reviewer'ın bakması iyi olur.
5. Hak bitince identity adımı uyarı cümlesini söyler, sonra kapanış cümlesi de söylenirse aynı uyarı iki kez duyulabilir. Bu kozmetik bir sorun; chat testinde bakılmalı.
