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
→ 76.8 (complex-headings golden düzeltmesi, sonra cross-page görsel dedup — skor sabit kaldı)
→ 77.3 (text_to_html_blocks'un h2 sezgiseli sıkılaştırıldı — yalnızca book-with-images_966108'i etkiledi)
→ 77.4 (sayfada hiç çizilmeyen "hayalet" görsel kaynakları artık atlanıyor — images %90.4→%91.6)
→ **77.6 (görsel konumlandırma/interleaving + boyut filtresi düzeltmesi, iki golden `expected_image_count` hatası giderildi — images %91.6→%91.8, aşağıya bkz.)**

## Tamamlanan adaylar

- ~~`complex-headings_tu-rkiye-sigorta-klavuz`~~ — 2026-08-23'te düzeltildi (58.8→80.7).
  İkisi de golden veri hatası çıktı, pipeline koduna dokunulmadı: bir must_include ifadesi
  aslında her sayfada doğru şekilde filtrelenen gerçek bir footer'dı (T. L. SWAN'daki
  Faz4 deseniyle aynı), diğeri dar kapsamlı bir kerning/harf-aralığı tuhaflığı yüzünden
  eşleşmiyordu. Detay: `TAMAMLANANLAR.md`. Yan bulgu (aşağıdaki madde 1): aynı kitapta
  paragraf sayısı da düşük çıkıyor — 2026-08-24'te araştırıldı, font-boyutu sinyali
  gerektiren ayrı bir açık soru olduğu netleşti (madde 1'e bkz.).
- ~~Görsel dedup (madde 2'nin ilk alt-adımı: sayfa-aşırı/cross-page dedup)~~ —
  2026-08-24'te eklendi. Gerçek, kanıtlanmış bir bug'dı: golden set taranınca 16 kitapta
  cross-page duplikasyon bulundu (`book-with-images_966108`'de 205 görselin 148'i aynı
  bayt içeriği). Fix sonrası `book-with-images_966108`'de EPUB'daki dosya sayısı 205→57,
  golden `expected_image_count`e (57) TAM eşleşti. Fast eval skoru DEĞİŞMEDİ çünkü `images`
  metriği referans SAYISINI ölçüyor, benzersiz dosya sayısını değil (ayrı NOTES.md maddesi
  — metrik düzeltilebilir ama bu roadmap'in kapsamı dışı, eval framework'ün kendi işi).
  Detay: `TAMAMLANANLAR.md`. Görsel dedup + konumlandırma maddesinin KALAN kısmı (madde
  2, aşağıda) hâlâ açık: konumlandırma (interleaving) ve boyut filtresi.
- ~~`mathematical` unsupported çelişkisi (eski madde 4)~~ — 2026-08-24'te düzeltildi.
  Golden veri hatası, pipeline koduna dokunulmadı: `mathematical_test-soruolar`'da
  `"Scanned by CamScanner"`, `mathematical_ujma`'da `"Universal Journal of Mathematics
  and Applications"` hem `must_include_phrases` hem `must_exclude_phrases`'te birdendi
  (aynı desen Faz4'te 10 kitapta düzeltilmişti) — ikisi de `must_exclude_phrases`'ten
  çıkarıldı. Yan bulgu: `unsupported: true` bayrağının skoru/gate'i etkilediği varsayımı
  YANLIŞ çıktı — `eval/evaluate.py`/`scoring.py`/`run.py`'de bu alana hiç referans yok,
  saf metadata; yani bu iki kitap da tam koşuda gerçek skorla giriyor (ayrı NOTES.md
  maddesi). Doğrulama: `mathematical_ujma` 64.1 [Fair], `mathematical_test-soruolar`
  28.8 [Failed] — ikisi de beklendiği gibi düşük kaldı (unsupported kategori, amaç
  yüksek skor değil, mantıksal çelişkiyi gidermekti). Detay: `TAMAMLANANLAR.md`.
- ~~"Hayalet" görsel kaynakları (madde 2'nin manuel doğrulaması sırasında bulunan yan bug)~~ —
  2026-08-24/25'te düzeltildi. `extract_embedded_page_images`, `page.get_images(full=True)`'in
  döndürdüğü HER xref'i sayfada gerçekten ÇİZİLİP çizilmediğine bakmadan çıkarıyordu —
  `book-with-images_966108` sayfa 17'de (madde 2'nin manuel testinde) `get_image_rects()`
  boş dönen bir xref (kaynak sözlüğünde var ama sayfada hiç görünmeyen) bulundu. Fix:
  `page.get_image_rects(xref)` boşsa görsel atlanıyor. Test: yeni fixture (düşük seviye
  `xref_set_key` ile Resources'a çizilmeden eklenen bir görsel) + regresyon testi,
  fix'siz haliyle kırmızı olduğu doğrulandı, suite 55/55 yeşil. Fast eval (16 kitap):
  77.3→77.4, `images` metrik ortalaması %90.4→%91.6, `book-with-images_966108` 54.9→57.4.
  Detay: `TAMAMLANANLAR.md`.
- ~~Madde 2'nin kalan iki alt-maddesi (görsel konumlandırma/interleaving + boyut filtresi)~~ —
  2026-08-25'te düzeltildi. Görseller artık sayfa sonuna değil, metin bloklarıyla birlikte
  TEK bir okuma-sırası akışında (`_build_interleaved_page_html`) PDF'teki gerçek konumlarına
  yerleştiriliyor — `book-with-images_966108` sayfa 17'de elle doğrulandı: artık gerçekten
  paragraf→figür→altyazı→paragraf sırasıyla üretiliyor. Boyut filtresi de ham piksel yerine
  sayfada GÖRÜNEN (nokta) boyutuna bakacak şekilde değişti (`MIN_EMBEDDED_IMAGE_DISPLAY_PT=30`).
  3 yeni regresyon testi (konumlandırma + iki boyut-filtresi senaryosu), suite 58/58 yeşil.
  Fast eval ilk koşuda görünen bir gerileme (77.4→76.5) iki golden `expected_image_count`
  hatasına (`english_molecules`, `two-column-academic_farkindalik-gelistirme-programi` —
  ikisinde de "içerik görseli" sanılan şey aslında dekoratif logo/CC-BY rozetiymiş, sayfa
  render'ları elle incelenerek doğrulandı) çıktı, golden düzeltilince 77.4→77.6. Detay:
  `TAMAMLANANLAR.md`.

## Sıradaki adaylar (öncelik sırasına göre)

### 1. `complex-headings_tu-rkiye-sigorta-klavuz` paragraf-sayısı düşüklüğü — font-boyutu sinyali gerekiyor
2026-08-24'te araştırıldı; `book-with-images_966108` ile "aynı kökten" olduğu varsayımı
YANLIŞ çıktı — o kitap ayrı bir bug'dan (`text_to_html_blocks`'un h2 sezgiseli, aşağıya
bkz. TAMAMLANANLAR) etkileniyordu ve düzeltildi (53.4→54.9). Bu kitap (skor 80.7,
`structure` hâlâ %44.8, 26 paragraf üretiliyor, golden [58, 86] bekliyor) AYNI metrik
sorununu (paragraf yerine `<h2>` üretimi) yaşıyor ama farklı sebepten: sahte başlıklar
("Kaydır" x4, "Detay 1/2/3", "Kalan Limit") düz Türkçe kısa kelimeler — denklem/atıf/TOC
gibi metinsel bir ayrım sinyalleri yok, gerçek başlıklardan ("İntro", "Poliçe Bilgileri")
salt metinle ayırt edilemiyor.

**Sonraki adım:** Güvenilir ayrım için yazı tipi boyutu/kalınlığı gerekir (`_extract_text_blocks`
şu an `page.get_text("blocks")` kullanıyor, font bilgisi taşımıyor; `page.get_text("dict")`'e
geçmek gerekir) — bu tam olarak madde 3'teki (bölüm tespiti) font-heuristiği kararıyla aynı
mimari genişleme. Ayrı ele alınmamalı, madde 3 gündeme gelince birlikte değerlendirilmeli.

### 3. Bölüm tespiti (chapter detection) — ERTELENDİ, kullanıcı onayı gerek
Kullanıcı 2026-08-22'de "şimdilik dokunma" dedi. Sebep: ölçülebilir etki dar (golden
sette yalnızca 2-3 kitapta `expected_chapters` dolu), taranmış kitaplarda font-boyutu
heuristiği eklemek OCR'ı plan fazında bir kez daha çalıştırmayı gerektirir (maliyet
ikiye katlanabilir). Detay: `NOTES.md` satır 56-57. Not: madde 1 (complex-headings'in
paragraf-sayısı sorunu) de aynı font-boyutu sinyaline ihtiyaç duyuyor — gündeme gelirse
ikisi birlikte değerlendirilmeli.

**Yeniden gündeme gelirse önce sorulacak:** Örneklem sayfa mı (hızlı, bazı bölümleri
kaçırabilir) yoksa tüm sayfaları OCR'lama mı (yavaş, tam)?

## Diğer (bu roadmap'in kapsamı dışı, ayrı konular)

`NOTES.md`'deki diğer maddeler (rate limiting, `process_chunk` egress israfı,
`ConvertJobStatus.PROCESSING`, ödeme/webhook konuları vb.) bu dönüşüm-kalitesi
çalışmasıyla ilgisiz, ayrı takip ediliyor.
