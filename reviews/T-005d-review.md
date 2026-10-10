# T-005d review (etiket adımsız kapanış, güvenli açılış)

Rapor: tasks/T-005d-report.md. Kod değiştirmedim, Freya'ya istek atmadım. `python3 -m unittest`: 98 test geçiyor.

## Karar: merge edilebilir
Kapanış türetmesi HEAD'deki (62a6284) etiket adımlı sürümle davranış olarak birebir aynı (aşağıdaki bağımsız karşılaştırma). Açılış değişiklikleri istenen dört şeyi yapıyor. Düzeltme gerektiren bir hata yok; iki küçük bulgu (1, 2) bir sonraki işte kapatılsın, geri kalanı ilk onaylı chat testinde doğrulanacak.

## 1. Kapanış yönlendirmesi

### Yöntem (testlerden bağımsız)
62a6284'ü `git archive` ile geçici klasöre çıkardım (repo'ya dokunmadan), eski ve yeni builder'ı Brief A ve B fixture'larından ürettim. `closing`'e (eski sürümde `close_<durum>` etiket adımlarına) giden geçişi olan her kaynak adım için (12 adım × 2 fixture) kendi koşul değerlendiricimle 6.000 rastgele değişken ataması çalıştırdım (eksik, boş, operand'lar, `true/True/false/False`, 0/1/2, bilinmeyen değer). Eski taraf: ilk tutan geçişin hedefi ve etiket adımının yazdığı durum. Yeni taraf: ilk tutan geçiş ve `derive_close_state()` kodunu gerçekten `exec` ederek bulduğu durum. Koda yazılmış durumla çalışan adımlar (`opening_unclear`, `check_offer`, `confirmation_progress`) türetmeden önce `close_state` yazıyor; onları ayrı doğruladım (aşağıda). Sonuç:

- Kaynak adım başına durum eşleşmesi: **0 sapma**, A ve B için (tüm 12 kaynak adım). Bu, öncelik sırasının (özel yol, müzakere, hesap, kimlik, geri arama, üçüncü kişi, açılış) eskisiyle çakışan durumlarda aynı sonucu verdiğini gösteriyor, yalnızca tek tek kuralları değil birden çok kuralın aynı anda tuttuğu artık-değişken durumlarını da.
- Tek fark: eski `opening_unclear → opening` dönüşü yeni `opening_reask`'a gidiyor (bilinçli değişiklik).
- Durumdan sonuca (outcome/reason): `TABLE` ve `choose()` değişmedi, yalnızca aday olarak `derive_close_state()` veriyor; durum aynı olduğundan outcome/reason aynı.

### İstenen öncelik senaryoları
- **Söz kaydı + aktarma:** `promise_recorded` `confirmation_progress` tarafından açıkça yazılıyor ve her türetme kuralını yeniyor; ayrı olarak `choose()` içindeki "kayıtlı söz varsa `promise` kazanır, `wins_over_promise` hariç" kuralı aynen duruyor. Aktarma (`special:<id>`) söz kaydından sonra tetiklenirse seçilen satırın `wins_over_promise` değeri belirler: eskisiyle aynı.
- **Kimlik başarısız + kapatma:** `identity_failed` kuralına "doğrulanmamış" koşulu eklenmiş. Bu, "doğrulandı ama kalan deneme 0" artığının sonraki bir kapanışta yanlışlıkla `identity_failed` okunmasını engelliyor. Karşılaştırmada eskisiyle uyumlu (eski sürümde doğrulanma geçişi zaten önce geliyordu).
- **Özel yol + söz:** `special:<id>` kuralı listenin başında; kayıtlı söz varsa `choose` yine `wins_over_promise` kuralına bakıyor.
- **Hang-up hook'u:** `_hangup_hook_code` `derive_close_state()` kodunu `closing` ile aynı üretici parçadan (`_close_state_derivation_code`) alıyor ve `candidates = [derive_close_state(), ...]` ile kullanıyor. Aynı koşullar, aynı sıra. Fail-closed URL düzeni (T-005c önerisi) hook'ta uygulanmış.
- **Koşul tablosunun tek kaynaktan gelmesi:** kaynak adımın `closing` geçişi `rules[state]` ile üretiliyor (`to_closing`), türetme kodu aynı `close_rules(spec)` listesinden; ayrışma mümkün değil. Ek olarak `TAGGED_CLOSE_STATES` dışında etiket adımı üretilemiyor (`internal:` hatası).
- Eski 18 etiket adımı gitmiş (A: 18 → 2, B: 16 → 2; kalanlar `close_turn_limit`, `close_special_tool_failed`). Bu ikisinin nedenleri (engine'in değişken yazmaması) makul.

### Bulgular
- **(Düşük, TO-CONFIRM) Türetme artık code'un `vars`'ında flatten edilmiş engine anahtarlarını okumasına bağlı.** `account_failure_count`, `schedule_callback_failure_count`, `schedule_callback_response.data.ok`, `special_result_<id>`, `identity_attempts_left`. Kit bunun lehine: `tools-and-code.md:264-277` (flatten `_response.*` ve sayaçlar değişken tablosunda), `:328` (kod düğümü sayacı), `:465` (önceki api düğümünün sonucu sonraki kod düğümünde `vars`'tan erişilebilir). Yine de doğrulanmadı. Görünmezse yalnızca `account_failed` ve sayaç yolundan gelen `callback_failed` `default` satırına düşer (yanlış outcome, çağrı yine kapanır). Rapor TO-CONFIRM 2 bunu zaten yazıyor; ilk onaylı chat testinde hesap hatası (kasıtlı bozuk müşteri) vakasıyla bakılsın.
- **(Bilgi) `not_equals` ve boş değişken:** `identity_failed` kuralı `identity_verified not_equals true/True` içeriyor. Motorun boş değişkende `not_equals`'u ne yaptığı kitte yazılı değil. `holds()` "boş = eşit değil" kabul ediyor. Karşılaştırmamı bu iki yorumla da yaptım: farklı olduğu tek durum `identity_attempts_left < 1` iken `identity_verified` hiç yazılmamış; ikisi aynı `verify_identity` yanıtından eşleniyor, pratikte birlikte yazılıyorlar. Risk yok, fakat istenirse `identity_verified equals false/False` ile sağlamlaştırılabilir.

## 2. Açılış

| Kontrol | Sonuç |
|---|---|
| Selamlaşma ("Hello?") deneme sayılmıyor mu | **Evet.** Çerçeve değeri `greeting` (`spec.OPENING_GREETING_VALUE`) extraction `enum_values`'a ekleniyor; hiçbir geçişte yok, yani adım yerinde kalıyor, `opening_unclear` sayacı artmıyor. Spec kendi seçeneklerinde `greeting` kullanırsa yükleme `SpecError` ile duruyor. Her iki fixture'da enum: customer, third_party, unclear, declined, greeting. Tur sınırı (`max_turn_transition`) sonsuz selamlaşmaya karşı koruma; `opening` ve `opening_reask` ikisinde de var. |
| Tanıtım tekrarlanmıyor mu | **Evet.** `opening_unclear` artık `opening`'e değil `opening_reask`'a dönüyor; o adımın görevi "tanıtımı zaten yaptın, sorulmadıkça tekrarlama; soruyu kısaca tekrar sor". `opening` `on_enter_first_entry_only: true` taşıyor ve artık hiçbir adım ona dönmüyor (test doğruluyor). |
| Geri dönüşte agent sessiz kalmıyor mu | `opening_reask` ayrı, kendi varsayılan giriş davranışına sahip bir adım (bayrak yok), yani her girişte konuşuyor. Bayrak yalnızca `opening`'de ve ona geri dönülmediği için sessizlik riski yok. Bu, T-004 N7 uyarısına uygun doğru tasarım. Kanıt ilk chat testinde (TO-CONFIRM 3, 4). |
| Tanıtım/kayıt bilgisi kuralı | **Var.** Sistem prompt'una genel kural: "bu tanıtımı bu çağrıda henüz yapmadıysan, müşteri ne derse desin sonraki mesajında önce yap: {introduction}". Metin spec'teki `agent.introduction`'dan; brief değeri kodda yok. |

### Bulgular
- **(Orta-Düşük) `opening_reask` global node kapsamına girmiyor.** `spec.py:205` `available_in`'de `opening`'e izin veriyor; `workflow.py` global node'ların `excluded_nodes` listesini kaynak adlarıyla kuruyor. Bir brief'te özel yol `opening`'de açıksa, `opening_reask`'ta (belirsiz cevap sonrası) o yol tetiklenmez (örnek: A kural 42 gibi "insan istiyorum" kuralı açılışta da geçerliyse). Mevcut fixture'larda `opening` kimsenin `available_in`'inde yok, yani şu an görünmüyor; hidden brief'te çıkabilir. **Düzeltme:** `available_in`'de `opening` varsa `opening_reask`'ı da kaynak say (global node'un `excluded_nodes` ve kaynak listesi için tek eşleme).
- **(Bilgi) Tanıtım kuralı her adımın prompt'una 40–90 token ekliyor.** En büyük adım A'da ~558, B'de ~524 token, bütçenin altında. Kural, model geçmişi kısaltılırsa geç bir adımda tanıtımı tekrar ettirebilir (rapor açık soru 1); varsayılan `keep_all`, düşük risk. İlk chat testinde tekrar görülürse kural yalnızca açılış adımlarına taşınsın.
- **(Bilgi)** "Who is this?" `greeting` örneği olarak açıklamada geçiyor: müşteri kim olduğunu soruyorsa agent tanıtımı zaten yaptıysa kısaca yanıt verip soruyu tekrar soruyor; yeterli. Çıkarıcı "Hello, yes this is X" cevabını `greeting` olarak etiketlerse adım bir tur daha sorar (zararsız).

## Hardcode
Brief değeri yok. `greeting` ve `hangup`/`hangup_unverified` iskelet sözcükleri; "Hello?" örnekleri genel. Sızıntı testi yeşil, `field` korumaları duruyor. Prompt'lar spec'ten dolduruluyor.

## Kurallara uyum
Freya isteği yok, testler çevrimdışı, stdlib. Her node'da `target_node` tekrarı yok (T-005b Fix 2 testi geçiyor).

## İlk onaylı testte bakılacaklar
1. Hesap hatası ve geri arama başarısız vakaları: `account_failed` / `callback_failed` doğru outcome'a düşüyor mu (`vars` görünürlüğü).
2. Araçsız kapanış yolu (global **kod** adımı + tts): cümle söyleniyor mu, ardından `closing`.
3. Müşteri "Hello?" ile açar: soru tekrar ediliyor mu, tanıtım ikinci kez söylenmiyor mu, `opening_unclear_count` artmıyor mu.
4. Belirsiz cevap sonrası `opening_reask` girişinde agent yalnızca soruyu soruyor mu.
5. Normal kapanışta ledger'da tek `close_call` (T-005c maddesi, hâlâ açık).
