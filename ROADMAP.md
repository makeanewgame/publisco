# PDF→EPUB Dönüşüm Kalitesi — Yol Haritası

Bu dosya, `modal_worker/eval/` framework'üyle sürdürülen kalite iyileştirme çalışmasının
güncel durumunu ve sıradaki adımları tutar — sohbet oturumu değişse bile buradan devam
edilebilsin diye. Tamamlanan işlerin detayı `TAMAMLANANLAR.md`'de, açık bug/bulgular
`NOTES.md`'nin "Sorunlar (Buglar)" bölümünde.

## Yöntem (her fazda aynı döngü izleniyor)

1. `pnpm test:conversion --fast` (veya `--book <id>`) ile mevcut durumu ölç, en düşük
   skorlu kitaplara bak
2. `--book <id>` ile o kitabın diagnostic çıktısını incele (`Missing phrases`,
   `Leaked excluded phrases`, component score'lar)
3. Kök nedeni doğrula — ham PDF'i doğrudan incele (`pymupdf`), golden veri hatası mı
   yoksa gerçek pipeline bug'ı mı ayır
4. Golden veri hatasıysa `metadata.json`'ı düzelt; pipeline bug'ıysa `converter.py`'de
   düzelt + yeni regresyon testi ekle (fix'siz haliyle testin gerçekten kırmızı
   olduğunu doğrula, sonra fix'i geri getir)
5. `pnpm test:conversion --fast` ile önce/sonra karşılaştır
6. `NOTES.md`/`TAMAMLANANLAR.md` güncelle
7. Kullanıcı "commitle" derse commit et — otomatik commit YOK

## Şu ana kadarki skor ilerlemesi (fast eval, 16 kitap)

43.5 → 47.6 (Faz1) → 52.8 (Faz2) → 54.8 (Faz3) → 63.7 (golden exclude-phrase denetimi)
→ 68.7 (aynı denetim, quote-normalizasyon öncesi) → **75.4 (Faz4 — en güncel)**

## Sıradaki adaylar (öncelik sırasına göre)

### 1. `complex-headings_tu-rkiye-sigorta-klavuz` — hızlı kazanç, düşük efor
Skor: 58.8. İki `must_include_phrase` kayıp, ikisi de zaten teşhis edildi:
- `"Müşteri Platformu Sağlık Kullanıcı Kılavuzu"` — kapak sayfasının ham metninde
  harfler arasına sahte boşluk giriyor (`"S ağ lık K u llan ıc ı Kılavu zu"`), muhtemelen
  kapak tasarımındaki harf aralığı (kerning) PyMuPDF'in kelime sınırı sezgisini bozuyor.
- `"www.turkiyesigorta.com.tr"` — ham PDF'te tam haliyle var ama üretilen EPUB metninde
  YOK (uçtan uca doğrulandı). Muhtemelen kısa/tek satırlık bu blok margin ya da noise
  filtresine takılıp siliniyor.

**Sonraki adım:** `_extract_text_blocks`/`_is_in_margin`/`_is_noise_block`'u bu sayfa
üzerinde adım adım izleyip URL bloğunun tam olarak hangi filtrede düştüğünü bul. Kerning
sorunu için PyMuPDF'in `get_text("words")` çıktısına bakıp boşluk-birleştirme sezgisi
eklenip eklenemeyeceğini değerlendir (riskli olabilir — genelleşebilir mi, tek kitaba mı
özel, önce kontrol et).

### 2. `book-with-images_966108` paragraf eksikliği — önce teşhis gerekiyor
Skor: 53.4, `structure` %22.9. 699 paragraf üretiliyor, golden `expected_paragraph_range`
[3051, 4576] bekliyor. **Henüz doğrulanmadı**: gerçek bir pipeline bug'ı mı (tablo-ağırlıklı
sayfalarda paragraf/tablo birleştirme sorunu), yoksa golden verideki tahminin kendisi mi
yanlış (tahmin, gerçek pipeline çalıştırılmadan ham blok sayısından yapılmıştı — tablo
ağırlıklı belgelerde bu tahmin yöntemi abartılı çıkabilir).

**Sonraki adım:** Kitabın birkaç sayfasını `_extract_text_blocks` ile adım adım işleyip
kaç ham blok / kaç nihai paragraf üretildiğini elle say, PDF'in o sayfalarını görsel
olarak (`page_to_image_bytes` ile) kontrol et. Gerçek kayıp varsa nerede olduğunu bul;
yoksa golden `expected_paragraph_range`'i gözlenen gerçek sayıya göre kalibre et.

### 3. Görsel dedup + konumlandırma (Faz 2'den açık kalan sınırlama)
`extract_embedded_page_images` (`converter.py`) üç bilinen sınırlamayla MVP bırakılmıştı
(detay: `NOTES.md` satır 47):
- Sayfa-aşırı dedup yok (aynı görsel her sayfada tekrarsa ayrı dosya olarak ekleniyor)
- Konumlandırma yaklaşık (görseller sayfanın SONUNA ekleniyor, gerçek konumuna değil)
- Boyut filtresi ham piksel boyutuna bakıyor, sayfadaki görünen/ölçeklenmiş boyuta değil

**Sonraki adım:** Sayfa-aşırı dedup en düşük riskli/en yüksek getirili parça gibi
görünüyor (xref bazlı bir `seen_xrefs`'i sayfa döngüsü dışına, chunk/reduce seviyesine
taşımak) — önce onunla başlanabilir. Tam interleaving (blok-seviyesi y-koordinat
sıralaması) daha büyük bir refactor, ayrı bir alt-adım olarak ele alınmalı.

### 4. Bölüm tespiti (chapter detection) — ERTELENDİ, kullanıcı onayı gerek
Kullanıcı 2026-08-22'de "şimdilik dokunma" dedi. Sebep: ölçülebilir etki dar (golden
sette yalnızca 2-3 kitapta `expected_chapters` dolu), taranmış kitaplarda font-boyutu
heuristiği eklemek OCR'ı plan fazında bir kez daha çalıştırmayı gerektirir (maliyet
ikiye katlanabilir). Detay: `NOTES.md` satır 56-57.

**Yeniden gündeme gelirse önce sorulacak:** Örneklem sayfa mı (hızlı, bazı bölümleri
kaçırabilir) yoksa tüm sayfaları OCR'lama mı (yavaş, tam)?

### 5. `mathematical` unsupported çelişkisi — en düşük öncelik, kozmetik
`mathematical_test-soruolar` / `mathematical_ujma`'nın golden metadata'sında aynı ifade
hem `must_include_phrases` hem `must_exclude_phrases`'te (mantıksal çelişki, aynı desen
Faz4'te 2 kitapta düzeltilmişti). `unsupported: true` olduğundan gerçek skora girmiyor
gibi görünüyor — düzeltilirse basitçe `must_exclude_phrases`'ten çıkarılmalı. Detay:
`NOTES.md` satır 48. Ayrıca `mathematical_singular-integrals`'te bir MuPDF layer uyarısı
var (satır 49), `mathematical` desteği gerçekten ele alınırsa incelenmeli.

## Diğer (bu roadmap'in kapsamı dışı, ayrı konular)

`NOTES.md`'deki diğer maddeler (rate limiting, `process_chunk` egress israfı,
`ConvertJobStatus.PROCESSING`, ödeme/webhook konuları vb.) bu dönüşüm-kalitesi
çalışmasıyla ilgisiz, ayrı takip ediliyor.
