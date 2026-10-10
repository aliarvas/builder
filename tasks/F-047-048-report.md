# F-047 / F-048 raporu: söylenen metin müşteriye hitap etsin; tanıtım yalnız açılışta

**Geliştirici:** claude-dev · **Tarih:** 2026-10-11

## Özet

- **Testler:** `python3 -m unittest` 234 testin hepsini geçiyor; 9'u yeni (`tests/test_spoken_text.py`). Sızıntı testi yeşil. `docs/PROMPTS.md` yeniden üretildi.
- **Kısıtlar:** Freya yok, commit yok, `env.sh` yok.
- **Dokunulmayanlar:** `selftest.py` ve `docs/` (PROMPTS.md hariç).
- **UAT:** "docs/ dışında kal" talimatı nedeniyle `docs/UAT-FINDINGS.md`'deki F-047 ve F-048 durumlarını **güncellemedim**. Önerilen durum: "fixed offline (F-047/048 task), retest pending".

**Değişen ve yeni dosyalar:**

- Kod: `builder/spoken.py` (yeni), `builder/workflow.py`, `builder/extract.py`, `builder/prompts.py`.
- Fixture'lar:
  - `tests/fixtures/spec-brief-a.json` ve `spec-brief-b.json` (B'nin tek satırlık biçimi korundu);
  - `tests/fixtures/extract/brief-a-replies.json`;
  - yeni `tests/fixtures/extract/brief-a-v11-extracted.json` (sürüm 11'in canlı spec'i).
- T-006b referansları: `tests/briefs/*/reference-spec.json`.
- Testler: `tests/test_multi_step.py`, `tests/test_prompt_budget.py`.

## F-047: söylenen metin müşteriye hitap etmeli

**Ne kadar yaygın:** Dedektör kayıtlı canlı spec'lere uygulandı. Sorun tek bir koşuyla sınırlı değil:

- sürüm 11 (`brief-a.spec.json`): 14 alan;
- f040 ve t006 koşuları: 7–35 alan;
- elle yazılmış fixture'lar: 0.

Örnekler: "Thank the customer and say goodbye.", `Say: "You will receive…"`, "Say that payments can take one business day to appear.", "Do not argue with the customer.", "Offer to connect the customer…".

**Dedektör (`builder/spoken.py`, genel İngilizce sözcükler, brief değeri yok):**

- **`agent_directed(text)`** üç durumda neden döndürüyor:
  - "the customer / the caller / the person …" geçiyorsa; "the customer support team" gibi hizmet adları hariç;
  - bir araç adı, alan adı ya da kod geçiyorsa;
  - bir cümle ajana yönelik emir kipiyle başlıyorsa: say, tell, ask, offer, explain, close, do not, never, take no … vb.

  "Thank you", "Please …" ve "Call us …" gibi müşteriye dönük kalıplar serbest.
- **`spoken_words(text)`:** `Say: "…"` biçimini açıyor, çünkü iki noktadan sonraki cümle zaten müşteriye söylenecek kelimeler. "Say that …" (dolaylı anlatım) açılmıyor ve hata sayılıyor.

**Extraction (`extract.py`, `prompts.py`):**

- **Doğrulanan alanlar:** `agent.introduction`, `agent.wait_line`, `identity.exhausted_say`, `outcomes[].say`, `special_paths[].say` ve `special_paths[].ask`.
- **Hata ve onarım:** Ajana hitap eden metin hata veriyor ve onarıma gidiyor. Mesaj: "is said to the customer word for word; write the exact words the agent says to the customer (for example "Thank you for your time. Goodbye."), not an instruction to the agent: <neden>".
- **Son tur:** Bu tür hatalar son turda uyarıya düşüyor ve build'i durdurmuyor. Renderer'daki son çare devreye giriyor.
- **Prompt'lar:** `introduction`, `exhausted_say`, outcome `say` ve özel yol `say` artık açıkça "müşteriye söylenecek birebir kelimeler, talimat değil" istiyor; karşı örnek ve doğru örnek veriliyor. "Code checks" listesine de bir madde eklendi.

**Renderer'daki son çare (`workflow.py`, `speakable_spec`):** `--spec` ile gelen her spec için de geçerli. Her değişiklik trace'te `warning: spoken_fallback <yol>: <neden>; …` olarak görünüyor.

| Alan | Son çare |
|---|---|
| outcome `say` (kapanış cümlesi) | `CLOSING_FALLBACK_SAY`: "Thank you for your time. Goodbye." |
| özel yol `say` | `SPECIAL_SAY_FALLBACK`: "Thank you for letting me know." (yeni prompt) |
| özel yol `ask` | Sabit tts yerine `on_enter: llm`; model soruyu kendi kelimeleriyle tek kısa soru olarak soruyor (`SPECIAL_ASK_PHRASED_TEMPLATE`, yeni). Soruyu atlamak, örneğin transfer onayını, daha kötü olurdu. |
| `agent.wait_line` | builder varsayılanı (F-043) |
| `introduction`, `exhausted_say` | Yalnız extraction'da doğrulanıyor. Bunlar prompt'ta modele verilen alanlar (tts değil); model cümleyi kendisi kuruyor. |

**Fixture güncellemesi:** Fixture A ve B'deki talimat biçimli `introduction` ve `exhausted_say` metinleri müşteriye söylenen cümlelere çevrildi. Kayıtlı cevaplar ve T-006b referansları da aynı şekilde güncellendi. Sentetik fixture'da bu iki prompt alanı talimat olarak duruyor; renderer'ı etkilemiyor.

## F-048: tanıtım yalnız açılışta

- "Henüz tanıtım yapmadıysan önce yap" satırı her adımın gördüğü sistem prompt'undan kaldırıldı. Üçüncü kişi adımı tanıtımı bu yüzden tekrarlıyordu.
- Kural artık yalnızca açılış adımının görev metninde: "Your first words in this call, whatever the customer said, and only once: …".
- Açılış her çağrının ilk adımı ve ajan ilk konuşan taraf. `opening_reask` zaten "tanıtımı tekrarlama" diyor; açılıştan önce tetiklenebilen başka bir adım yok.
- Bir durum değişkenine gerek kalmadı: kural yalnızca ilk ulaşılan adımda. Bu, görevdeki ikinci seçenek.
- **Yan etki:** Sistem prompt'u kısaldı ve her adım ~45 token azaldı. Etiketli A+B'de `negotiate` ~1256'ya indi, etiketsiz A+B ~1538.

## Testler (`tests/test_spoken_text.py`)

- **Dedektör:** 8 müşteri cümlesi geçiyor, 10 talimat yakalanıyor (`Say:` açma dahil).
- **Sürüm 11 canlı spec:** Render sonrası söylenen hiçbir sabit cümle talimat değil (tts girişleri ve kapanış tablosu). En az 11 `spoken_fallback` uyarısı var.
- **Fixture A:** Değişmiyor, `spoken_fallback` yok.
- **Her alanın son çaresi:** `Say:` açılıyor; kapanış, özel yol ve `wait_line` için son çare kullanılıyor; `ask` model tarafından soruluyor; uyarılar yazılıyor.
- **Extraction:** Talimat onarıma gidiyor. Hiç düzelmezse build durmuyor; uyarı yazılıyor ve render son çareyi kullanıyor. `introduction` ve `exhausted_say` da onarıma gidiyor.
- **Tanıtım:** Fixture A ve sürüm 11'de tanıtım yalnızca açılışta; sistem prompt'unda ve üçüncü kişi adımında yok.
- **Diğer:** `test_multi_step.py`'deki T-005d tanıtım testi yeni yerleşime göre güncellendi. Bütçe testleri sabit token sayılarına bağımlı olmaktan çıkarıldı.

## Canlı tekrar (CTO)

- **Brief A resmi komut:**
  - trace'te `spoken_fallback` uyarıları ne kadar? Prompt düzeltmesi tuttuysa az ya da sıfır olmalı;
  - kapanışta müşteri bir talimat duyuyor mu?
- **`third_party_close` vakası:** Üçüncü kişi adımında tanıtım tekrar ediyor mu?

## F-049/050

**Kapsam:** `docs/` altında yalnızca `PROMPTS.md` yeniden üretildi. UAT'taki F-049 ve F-050 durumlarını güncellemedim ("docs/ dışında kal"). Önerilen durum: "fixed offline, retest pending".

### F-050: passthrough `api_request` adımlarında `tts` girişi yok

- **`account`:** `on_enter` yeniden `silent`.
- **Bekleme cümlesi** artık kimlik adımının prompt'unda: "After the last question, ask nothing more; say the answers matched, then say: {wait_line} Give no account details yet."
  - `{wait_line}` spec'teki `agent.wait_line`'dan geliyor (F-047 temizliğinden geçmiş haliyle); yoksa `ACCOUNT_WAIT_LINE` varsayılanı.
  - Cümleyi model söylüyor; bu kimlik adımının son mesajı, yani bir konuşma adımı.
- **İkinci passthrough `api_request` (görevdeki "tüm passthrough api_request"):** Araçlı ve model alanı gerektirmeyen özel yollar, örneğin transfer, cümlelerini `api_request` adımında `tts` ile söylüyordu. Bu da aynı riskteydi.
  - Şimdi cümleyi önce gelen bir `code` adımı söylüyor (`<adım>`, `tts`).
  - Araç sessiz bir `api_request` adımında çalışıyor (`<adım>_call`).
  - Başarı ve başarısızlık yönlendirmesi aynı kaldı.
  - `code` + `tts` biçimi canlıda zaten çalışıyor: kapanış cümlesini `closing_say` böyle söylüyor ve PUB-01 geçti.
- **Bütçe:** Kimlik adımı biraz uzadı ama hedefin altında: sürüm 11 spec'inde 961, etiketli A+B'de 1065 token.

### F-049: kimlik adımına girişte kontrol

- Açılıştan sonra yeni bir `identity_check` kod adımı (passthrough, sessiz) geliyor:
  - `identity_verified` true ya da True ise doğrudan `account`'a geçiyor;
  - değilse `identity`'ye (son geçiş `always`).
- Açılışın "müşteri cevap verdi" geçişi artık `identity_check`'e gidiyor. Deterministik bir koşul; model çağrısı yok.
- **Sınır:** F-049'daki gibi platform turu durumuyla birlikte geri alırsa değişken de sıfırlanır; bu adım o durumu düzeltemez. Bir adım yeniden oynatıldığında ya da kimlik adımına yeniden girildiğinde, değişken korunmuşsa güvenli.

### Testler

- **Yeni:**
  - Fixture'larda ve kayıtlı extraction spec'lerinde **hiçbir** `api_request` adımı `tts` girişine sahip değil; hepsi passthrough ve `silent`.
  - Kimlik prompt'u varsayılan bekleme cümlesini, spec'te varsa spec'in cümlesini içeriyor; `account` sessiz.
  - Açılış `identity_check` üzerinden geçiyor; `identity_check` true/True için `account`'a, değilse `identity`'ye yönlendiriyor.
- **Güncellenen:**
  - `test_multi_step.py`: özel yol adımı artık `code` + `_call` (`api_request`, sessiz). Araç argümanı testi `_call` adımına bakıyor. Kapsam testi `_call` çıkışlarını izliyor.
  - F-043 ve F-047 testleri: bekleme cümlesi artık kimlik prompt'unda.
- **Sonuç:** `python3 -m unittest` 243 testin hepsini geçiyor. `docs/PROMPTS.md` yeniden üretildi.

### Canlı tekrar (CTO)

- PUB-07: kimlik turunda 502 ya da geri alma yok mu?
- Kimlikten sonra bekleme cümlesi modelin son mesajında geçiyor mu?
- Platformun Türkçe dolgusu (F-043) geri geliyor mu? Gelirse bu ayrı bir organizatör sorusu.
- Bir transfer yolunda cümle önce söylenip sonra transfer çağrılıyor mu?
