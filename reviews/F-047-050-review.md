# F-047/048 ve F-049/050 review (söylenen metin, tanıtım, sessiz api adımları, kimlik girişi)

Rapor: tasks/F-047-048-report.md (iki bölüm); yeni `builder/spoken.py`. Kod düzenlemedim, Freya'ya ve modele istek atmadım. `python3 -m unittest`: 243 test geçiyor. Beş spec'i (fixture A, B, sentetik, canlı sürüm 11 çıkarması, f041-a çıkarması) kendim render ettim ve inceledim.

## Karar: merge edilebilir
İstenen beş şey de uygulanmış ve doğrulandı. Kalanlar canlı doğrulama maddeleri ve iki küçük not.

## 1. Söylenen alan doğrulaması (F-047): doğrulandı
- **Dedektör (`spoken.py`):** 12 müşteriye dönük cümleyi ("Thank you for your time. Goodbye.", "I am transferring you to a colleague now.", "Payments can take one business day to appear.", "We will call you back…", "Can I help you with anything myself before I transfer you?" …) denedim: hiçbiri yanlış bayraklanmadı. 12 talimat cümlesinin hepsi yakalandı ("Thank the customer and say goodbye.", "Say that payments…", "Do not argue with the customer.", "Offer to connect the customer…", "Take no promise.", "Close the call as paid.", "Ask nothing else.", "The customer should be told…", araç adı içeren cümle, "Read the promise back."). `Say: "…"` biçimi açılıyor ve açılan metin müşteriye hitap ediyor.
- **Extraction:** `agent.introduction`, `agent.wait_line`, `identity.exhausted_say`, `outcomes[].say`, `special_paths[].say` ve `.ask` doğrulanıyor. Talimat metni denediğimde her biri hata verdi ("is said to the customer word for word; write the exact words the agent says…, not an instruction to the agent: <neden>"), `ask` ayrıca "ends with ?" kuralından; son turda bu hatalar uyarıya düşüyor (`spoken_soft`) ve build durmuyor.
- **Renderer son çaresi (`speakable_spec`):** `--spec` yoluyla gelen spec'ler için de çalışıyor; her değişiklik `warning: spoken_fallback <yol>: …` olarak izde. Sürüm 11 canlı spec'inde 13 uyarı çıkıyor (talimat biçimli metinler gerçekten yaygınmış), fixture A/B'de ve f041-a'da 0. Kapanış cümlesi `CLOSING_FALLBACK_SAY`'e, özel yol cümlesi `SPECIAL_SAY_FALLBACK`'e düşüyor; `ask` fallback'i sabit satır yerine modelin kendi sorusu (`on_enter: llm`) — transfer onayını atlamaktan iyi.
- Küçük not: "Confirm that …" gibi müşteriye dönük bir emir (ör. onay isteyen bir `ask`) "agent-directed" sayılır (`confirm that` fiil listesinde); hata onarımla düzelir, nadir. `wait_line`'da `{{` ve uzunluk denetimi hâlâ yok (F-043-044 review notum).

## 2. Tanıtımın tekrarı (F-048): doğrulandı, durum değişkeni yerine yerleşimle sınırlanmış
- Rapor ikinci seçeneği seçmiş: değişken yok, kural yalnızca açılış görevinde ("Your first words in this call, whatever the customer said, and only once: …"). Sistem prompt'unda tanıtım kuralı yok, `third_party` görevinde de yok (kendim kontrol ettim). `opening_reask` "tanıtımı tekrarlama" diyor. Açılış çağrının ilk adımı olduğu ve başka bir adım ondan önce tetiklenemediği için değişken gereksiz; savunulabilir. Her adımın prompt'u ~45 token kısaldı (etiketli A+B `negotiate` ~1256).

## 3. Passthrough `api_request` adımlarında `tts` yok (F-050): doğrulandı
- Beş spec'te (A, B, sentetik, v11, f041-a) tüm `api_request` düğümlerini tarayan kendi denetimim: `on_enter` `tts` olan hiçbiri yok; passthrough `api_request` adımlarının hepsi `silent`. `account` artık sessiz; bekleme cümlesi kimlik adımının prompt'unda ("…say the answers matched, then say: Thank you. One moment while I check your account. Give no account details yet.") ve spec'in `wait_line`'ı kazanıyor.
- **Özel yollar:** araçlı yollarda cümleyi `code` + `tts` adımı (`special_<yol>_go`, ya da global düğümün kendisi) söylüyor, araç sessiz bir `api_request` adımında (`…_call`) çalışıyor; başarı → `closing`, hata → `close_special_tool_failed` korunmuş. Üretilen düğümlerde doğruladım (`special_human_go`: code/tts → `special_human_go_call`: api_request/silent → closing | close_special_tool_failed). `code`+`tts` kalıbı `closing_say` ile canlıda zaten çalışıyordu.
- **Not (TO-CONFIRM, canlı):** bekleme cümlesi artık kimlik adımının *son* mesajında söyleniyor ve bu, doğrulayıcı tool sonucu geldikten sonra yönlendirmenin modelin cümlesinden önce çalışıp çalışmadığına bağlı (kit "agent can acknowledge and move in the same message" diyor, ama F-021'de sohbet yolunda yönlendirme bastırılabiliyor). Cümle söylenmezse hata değil, yalnızca sessiz bir bekleme olur (Türkçe dolgu geri gelebilir). Rapor bunu canlı maddeler arasında listelemiş.
- Küçük not: kimlik prompt'undaki "after the last question … say the answers matched" cümlesi, `verified` false dalının yanında duruyor; model sonuç gelmeden "matched" demez diye düzenlenmiş. Yine de bu cümleyi "only when verified is true" ile başlatmak (ör. zaten öyle: "verified is true: …") yanlış okunma riskini sıfırlar; mevcut hâli kabul.

## 4. Kimlik girişi (F-049): doğrulandı
- Açılıştan sonra yeni `identity_check` (passthrough `code`, sessiz): `identity_verified` true/True → `account`, aksi → `identity` (son geçiş `always`). Hem `opening` hem `opening_reask` müşteri cevabında `identity_check`'e gidiyor; `identity`'ye başka giriş yok (kontrol ettim). Deterministik, model çağrısı yok. Sınırı rapor doğru söylüyor: platform durumu ve değişkenleri birlikte geri alırsa bu adım düzeltemez; yalnızca değişken korunmuşken yeniden oynatmayı güvenli yapar.
- Global düğümlerin kaynak adımları değişmemiş (özel yollar: `negotiate`, `confirm_record`, `identity`, `opening`/`opening_reask`, ... eskisiyle aynı); yeni adımlar `excluded_nodes` kapsamında.

## Brief değeri ve kurallar
`spoken.py` ve yeni prompt metinleri genel İngilizce sözcüklerden oluşuyor; brief değeri yok, sızıntı testi yeşil. Freya/model isteği yok, stdlib. UAT'ta F-047..F-050 durumları geliştirici tarafından güncellenmemiş (belge dışı kalma talimatı); önerilen durum "fixed offline, retest pending".

## Canlı doğrulama için
Raporun listesi doğru; ek: resmî komutta `spoken_fallback` uyarı sayısı (prompt düzeltmesi tuttuysa az/sıfır), kapanışta müşterinin talimat duymaması, `third_party_close`'da tanıtımın tekrarlanmaması, PUB-07'de kimlik turunda 502/geri alma olmaması, bir transfer yolunda cümlenin aracı çağırmadan önce söylenmesi.
