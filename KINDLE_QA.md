# Kindle QA — Golden Set EPUB Kontrolü

Golden dataset'teki (`modal_worker/eval/golden/`) 47 gerçek kitabın EPUB çıktısı
Kindle'da elle gözden geçiriliyor (`eval/results/epubs/<book-id>.epub`, üretmek
için `pnpm test:conversion --save-epubs`, bkz. `modal_worker/eval/README.md`).

Amaç: `eval/` framework'ünün metrikleriyle yakalanamayan (görsel yerleşim,
okuma deneyimi, font/encoding garipliği gibi) sorunları bulmak. Bir bulgu
netleşince buradan `NOTES.md`'nin "Sorunlar (Buglar)" bölümüne taşınır (kök
neden + hangi kitap(lar)da gözlendiği ile), gerekiyorsa `ROADMAP.md`/
`TAMAMLANANLAR.md` de senkronlanır (bkz. `CLAUDE.md` "After Every Task").

Kontrol edilen kitabı `[x]`'e çevir, bulgu varsa satırın sonuna kısaca yaz
(bulgu yoksa "OK" yeterli).

## bad-ocr-layer
- [ ] `scanned_003` —
- [ ] `scanned_004` —
- [ ] `scanned_005` —

## book-with-footnotes
- [ ] `scanned_006` —

## book-with-images
- [x] `book-with-images_966108` — Abstract/İçindekiler/"1 Giriş"/Şekiller Dizini gibi başlıklar heading olarak çıkmamış; İçindekiler, Şekiller Dizini, Simgeler ve Kısaltmalar bölümleri çok kötü görünüyor (muhtemelen liste/tablo düzeni bozuluyor); yazının çevresindeki boşluklar (margin/padding) aşırı fazla. Ayrıca: φ/τ/σ gibi formül sembolleri Kindle'da kutu (□) olarak görünüyor — kök neden bulundu, bkz. NOTES.md (PUA glyph remap + Mathematical Alphanumeric Symbols font kapsama sorunu), kapsam dışı bırakıldı.
- [ ] `book-with-images_active-skills-for-reading-4` —
- [ ] `book-with-images_ankaranin-trekking-rotalari` —
- [ ] `book-with-images_astronomi-alfa-yayinlari` —
- [ ] `book-with-images_bilim-kitabi-alfa-yayinlari` —
- [ ] `book-with-images_dunya-tarihi-alfa-yayinlari` —
- [ ] `book-with-images_haritalarla-cografya` —
- [x] `book-with-images_mitoloji-kitabi-alfa-yayinlari` — Ön-metin sayfaları (kapak, İçindekiler, Katkıda Bulunanlar) kötü, ana mitoloji metni (tek sütun) düzgün. İki farklı kök neden bulundu, NOTES.md'ye eklendi: (1) çok-sütunlu İçindekiler/Katkıda-Bulunanlar sayfalarında PyMuPDF'in kendi blok segmentasyonu sütunları zaten birleştiriyor, bizim sütun-tespit kodumuza sıra gelmiyor; (2) kapak sayfasındaki dağınık/dekoratif başlık metinleri (afiş tarzı, doğrusal okuma sırası olmayan) anlamsız çıkıyor — bu daha genel bir sınırlama.
- [ ] `book-with-images_sanat-kitabi-alfa-yayinlari` —
- [ ] `book-with-images_sinema-kitabi-alfa-yayinlari` —
- [ ] `book-with-images_tarih-kitabi-alfa-yayinlari` —

## book-with-tables
- [ ] `book-with-tables_introductory-statistics` —
- [ ] `book-with-tables_table` —

## complex-headings
- [x] `complex-headings_tu-rkiye-sigorta-klavuz` — Bazı görseller düz siyah kutu olarak çıkıyor (ör. `page_1_img_0.png`, logo). Kök neden bulundu ve NOTES.md → Sorunlar (Buglar)'a eklendi: PDF'teki SMask (alfa kanalı) `extract_embedded_page_images`'te uygulanmıyor.

## english
- [ ] `english_molecules` —

## mathematical
_(golden set'te `unsupported: true` — skora dahil değil, yine de görsel/formül render'ı Kindle'da kontrol edilmeye değer)_
- [ ] `mathematical_franctional` —
- [x] `mathematical_gumusfenbil` — (1) "P-Function"daki 𝑃 Kindle'da görünmüyor — `mathematical_order-integrations`/`book-with-images_966108` ile aynı Unicode Mathematical Alphanumeric Symbols sorunu. (2) "Abstract" başlığı algılanmamış, önceki metadata satırı ve özet paragrafıyla tek blokta birleşmiş görünüyor — kök neden NOTES.md'ye eklendi: PyMuPDF'in kendi blok segmentasyonu "Abstract"ı ayrı bir blok olarak vermiyor, `mitoloji-kitabi`'deki İçindekiler bulgusuyla AYNI mekanizma (PyMuPDF blok birleştirmesi bizim işleme sırasından önce oluyor).
- [ ] `mathematical_integral` —
- [ ] `mathematical_matematik-ders` —
- [x] `mathematical_order-integrations` — Formüller (kesir, limit, üst/alt simge içeren tanımlar) tamamen dağılmış/anlamsız metin parçaları olarak çıkıyor (ör. "x f h x f d", "lim ) ("). Kök neden: taranmış değil, gömülü metin katmanı var ama PDF matematik dizgisini (kesir/limit/simge) ayrı ayrı konumlandırılmış küçük metin parçaları olarak tutuyor, bizim okuma-sırası birleştirmemiz bunları birbirine karıştırıyor. Golden metadata'da zaten `unsupported: true` ("heavy mathematical notation") — bilinen v1 kısıtlamasının somut teyidi, `mathematical_test-soruolar`'daki OCR-güven sorunundan farklı bir mekanizma (bkz. NOTES.md).
- [ ] `mathematical_perelman-poincare` —
- [ ] `mathematical_singular-integrals` —
- [x] `mathematical_test-soruolar` — Ciddi: 440 sayfalık taranmış kitapta EPUB'a yalnızca 13 görsel girmiş, kalan 427 sayfa OCR'ın ürettiği anlamsız metinle dolu (gerçek içerik kayboluyor). Kök neden bulundu ve NOTES.md → Sorunlar (Buglar)'a eklendi: `converter.py`'de OCR güven skoru kontrol edilmiyor, sadece "metin boş mu" bakılıyor.
- [ ] `mathematical_ujma` —

## multilingual
- [ ] `multilingual_arapc-a-kitap` —
- [ ] `multilingual_azerice-kitap` —
- [ ] `multilingual_azerice-kitap-2` — _(bkz. NOTES.md — images/ocr_quality regresyonu araştırılmayı bekliyor)_

## normal-text-novel
- [ ] `normal-text-novel_son-sans` —

## poor-quality-scan
- [x] `poor-quality-scan_dikenler-sehri` — Ciddi ve sistemik: paragraflar sürekli cümle ortasından bölünüyor, bazı sıradan cümle parçaları da yanlışlıkla `<h2>` başlık oluyor. Kök neden bulundu (bkz. NOTES.md) — muhtemelen sadece bu kitaba özgü değil, düşük kaliteli taranmış birçok kitabı (scanned-novel, bad-ocr-layer kategorileri) etkiliyor olabilir; eval'daki düşük skorlu `scanned_001`/`scanned_004`/`scanned-novel_sevgili-tas-kalbim` de aynı mekanizmadan etkilenmiş olabilir, doğrulanmadı.

## scanned-novel
- [ ] `scanned-novel_sevgili-tas-kalbim` —
- [ ] `scanned_001` —
- [ ] `scanned_002` —

## technical-with-code
- [ ] `technical-with-code_c-primer-plus` —
- [ ] `technical-with-code_cplus-conherince` —
- [x] `technical-with-code_functional-programing` — Kitap boyunca tekrar tekrar "Sayfa 2", "Sayfa 9", "Sayfa 25", "Sayfa 28", "Sayfa 30"... gibi başlıklar çıkıyor, altlarında görünür içerik yok. Kök neden bulundu (bkz. NOTES.md): bu sayfalar TAMAMEN BOŞ (metin/görsel/çizim yok, muhtemelen matbaa dolgu sayfaları) — pipeline boş sayfayı atlamak yerine görsel-sayfa fallback'ine düşürüp "Sayfa N" başlığı ekliyor. Basit ve düşük riskli bir fix fırsatı: boş sayfa tespit edilirse hiç eklenmemeli.
- [ ] `technical-with-code_progit` —

## turkish
- [ ] `turkish_bilimsel-makale-nasil-yazilir` —
- [ ] `turkish_carpik-ask` —

## two-column-academic
- [ ] `two-column-academic_arastima-makalesi` —
- [ ] `two-column-academic_attention-is-all-you-need` —
- [ ] `two-column-academic_elektrofarazi` — _(bkz. NOTES.md — sayfa 1 masthead sızıntısı bilinen küçük sınırlama)_
- [ ] `two-column-academic_farkindalik-gelistirme-programi` —
- [ ] `two-column-academic_vibe-coding` —
