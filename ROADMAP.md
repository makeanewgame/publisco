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
→ 68.7 (aynı denetim, quote-normalizasyon öncesi) → 75.4 (Faz4)
→ **76.8 (complex-headings golden düzeltmesi, sonra cross-page görsel dedup — skor sabit kaldı, aşağıya bkz.)**

## Tamamlanan adaylar

- ~~`complex-headings_tu-rkiye-sigorta-klavuz`~~ — 2026-08-23'te düzeltildi (58.8→80.7).
  İkisi de golden veri hatası çıktı, pipeline koduna dokunulmadı: bir must_include ifadesi
  aslında her sayfada doğru şekilde filtrelenen gerçek bir footer'dı (T. L. SWAN'daki
  Faz4 deseniyle aynı), diğeri dar kapsamlı bir kerning/harf-aralığı tuhaflığı yüzünden
  eşleşmiyordu. Detay: `TAMAMLANANLAR.md`. Yan bulgu (aşağıdaki madde 1'e eklendi):
  aynı kitapta paragraf sayısı da düşük çıkıyor — henüz araştırılmadı.
- ~~Görsel dedup (madde 2'nin ilk alt-adımı: sayfa-aşırı/cross-page dedup)~~ —
  2026-08-24'te eklendi. Gerçek, kanıtlanmış bir bug'dı: golden set taranınca 16 kitapta
  cross-page duplikasyon bulundu (`book-with-images_966108`'de 205 görselin 148'i aynı
  bayt içeriği). Fix sonrası `book-with-images_966108`'de EPUB'daki dosya sayısı 205→57,
  golden `expected_image_count`e (57) TAM eşleşti. Fast eval skoru DEĞİŞMEDİ çünkü `images`
  metriği referans SAYISINI ölçüyor, benzersiz dosya sayısını değil (ayrı NOTES.md maddesi
  — metrik düzeltilebilir ama bu roadmap'in kapsamı dışı, eval framework'ün kendi işi).
  Detay: `TAMAMLANANLAR.md`. Görsel dedup + konumlandırma maddesinin KALAN kısmı (madde
  2, aşağıda) hâlâ açık: konumlandırma (interleaving) ve boyut filtresi.

## Sıradaki adaylar (öncelik sırasına göre)

### 1. Paragraf-sayısı düşük çıkan kitaplar — önce teşhis gerekiyor
İki kitapta aynı açık soru var, muhtemelen ortak bir kök nedenleri olabilir:
- `book-with-images_966108`: skor 53.4, `structure` %22.9. 699 paragraf üretiliyor,
  golden `expected_paragraph_range` [3051, 4576] bekliyor (149 sayfalık, tablo-ağırlıklı
  bir tez).
- `complex-headings_tu-rkiye-sigorta-klavuz`: skor 80.7 ama `structure` hâlâ %44.8. 26
  paragraf üretiliyor, [58, 86] bekleniyor (mobil uygulama rehberi, kısa navigasyon/liste
  blokları ağırlıklı).

**Henüz doğrulanmadı**: gerçek bir pipeline bug'ı mı (tablo/liste-ağırlıklı sayfalarda
aşırı birleştirme), yoksa golden verideki tahminin kendisi mi yanlış (tahmin, gerçek
pipeline çalıştırılmadan ham blok sayısından yapılmıştı — bu iki format için de tahmin
yöntemi abartılı çıkmış olabilir).

**Sonraki adım:** Her iki kitabın birkaç sayfasını `_extract_text_blocks` ile adım adım
işleyip kaç ham blok / kaç nihai paragraf üretildiğini elle say, PDF'in o sayfalarını
görsel olarak (`page_to_image_bytes` ile) kontrol et. Gerçek kayıp varsa nerede olduğunu
bul; yoksa golden `expected_paragraph_range`'i gözlenen gerçek sayıya göre kalibre et.
İki kitap da aynı kökten çıkarsa (ör. Faz3'ün çok-satırlı-blok kuralı liste/tablo
formatlarında fazla agresif davranıyorsa) tek bir fix ikisini de düzeltebilir.

### 2. Görsel konumlandırma + boyut filtresi (Faz 2'den açık kalan, dedup hariç)
`extract_embedded_page_images` (`converter.py`) üç bilinen sınırlamayla MVP bırakılmıştı;
sayfa-aşırı dedup 2026-08-24'te düzeltildi (yukarıya bkz.), kalan ikisi açık:
- **Konumlandırma yaklaşık** — görseller sayfanın SONUNA ekleniyor, gerçek konumuna
  (paragraf arasına) değil; tam interleaving için blok-seviyesi y-koordinat sıralaması
  (`_extract_text_blocks`'un zaten yaptığına benzer) gerekir.
- **Boyut filtresi** ham piksel boyutuna bakıyor, sayfadaki görünen/ölçeklenmiş boyuta
  değil — küçük gösterilen büyük bir görsel ya da tersi yanlış filtrelenebilir.

**Sonraki adım:** Tam interleaving daha büyük bir refactor — `_extract_text_blocks`'un
zaten sayfa bloklarını (metin + görsel, x/y koordinatlarıyla) okuduğu noktaya görsel
bloklarını da (şu an `block[6] != 0` ile atlanıyor) dahil edip tek bir birleşik
sıralama üretmek gerekir. Önce küçük bir golden kitapta (`book-with-images_haritalarla-cografya`
gibi görsel-ağırlıklı, az sayfalı biri) elle denenip gerçek okuma deneyimine etkisi
görülmeli — bu, ROADMAP'teki diğer maddelerden daha büyük bir mimari değişiklik, ayrı
bir oturumda ele alınabilir.

**Not (2026-08-24):** Bu maddenin etkisini ölçmek için önce `eval/metrics/images.py`'nin
NOTES.md'de belirtilen ölçüm sorunu (occurrence vs benzersiz dosya sayısı) gözden
geçirilmeli — yoksa konumlandırma/boyut-filtresi düzeltmeleri de skora tam yansımayabilir.

### 3. Bölüm tespiti (chapter detection) — ERTELENDİ, kullanıcı onayı gerek
Kullanıcı 2026-08-22'de "şimdilik dokunma" dedi. Sebep: ölçülebilir etki dar (golden
sette yalnızca 2-3 kitapta `expected_chapters` dolu), taranmış kitaplarda font-boyutu
heuristiği eklemek OCR'ı plan fazında bir kez daha çalıştırmayı gerektirir (maliyet
ikiye katlanabilir). Detay: `NOTES.md` satır 56-57.

**Yeniden gündeme gelirse önce sorulacak:** Örneklem sayfa mı (hızlı, bazı bölümleri
kaçırabilir) yoksa tüm sayfaları OCR'lama mı (yavaş, tam)?

### 4. `mathematical` unsupported çelişkisi — en düşük öncelik, kozmetik
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
