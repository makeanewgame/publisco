Publisco conversion evaluation framework kuruldu — modal_worker/eval/, pipeline koduna hiç dokunmadan:
Ne var:
* runner.py / epub_reader.py — dönüştürmeyi lokalde (Modal'sız) çalıştırıp EPUB'ı metriklere çözer
* 7 metrik modülü: text completeness (recall/precision/n-gram overlap), duplicates, broken words, OCR confidence, structure/TOC, images, epubcheck validity
* scoring.py — onayladığın ağırlıklı model + hard gate'ler (epub_invalid → ≤59, completeness <%50 → ≤39) + Excellent/Good/Fair/Poor/Failed kategorileri
* golden/ — hybrid iki-katmanlı referans stratejisi (phrase-check + opsiyonel tam referans metin), 3 sentetik smoke kitap, add_book.py ile gerçek kitap ekleme aracı
* run.py CLI → kökten pnpm test:conversion [--smoke|--book X|--save-baseline|--variant|--compare]
* 22 yeni pytest testi (41/41 yeşil), eval/README.md
Doğrulama sırasında bulunan gerçek bug: assemble_epub'daki görsel EpubItem.uid'i dosya adıyla aynı ("images/page_2.jpg") — "/" karakteri geçersiz XML id, epubcheck bunu hata olarak işaretliyor ve framework skoru otomatik 59'a çekiyor. NOTES.md'ye eklendi, pipeline'a dokunulmadı (kural gereği).
Sıradaki adım (senin tarafında): 15-20 telifsiz PDF'i python -m eval.golden.add_book ile ekleyip metadata.json'ları doldurmak, sonra gerçek bir baseline kaydetmek — şu an baselines/baseline.json yalnızca smoke kitaplarla dolu.

cd modal_worker
.venv/bin/python -m eval.golden.add_book <pdf_yolu> <book-id> <kategori>
Örnek:

.venv/bin/python -m eval.golden.add_book ~/Downloads/kitap.pdf book-001-ornek normal-text-novel
Bu şunları yapar:
1. PDF'i eval/golden/books/book-001-ornek/input.pdf'e kopyalar
2. sha256'sını hesaplayıp manifest.json'a ekler
3. Doldurman gereken TODO alanlı bir metadata.json iskeleti oluşturur
Kategori olarak (normal-text-novel, scanned-novel, turkish, technical-with-code vb. — README'de 15 tanenin tam listesi ve kaynak önerileri var) seçim yapmalısın. Sonra metadata.json'daki language, must_include_phrases, expected_chapters gibi TODO alanlarını elle doldurman gerekiyor.


- [ ] | `normal-text-novel` | Project Gutenberg (EPUB'dan PDF'e dönüştürülmüş herhangi bir roman) |
- [ ] | `scanned-novel` | Internet Archive (`archive.org`) taranmış roman |
- [ ] | `poor-quality-scan` | Internet Archive, düşük çözünürlüklü/eski tarama |
- [ ] | `bad-ocr-layer` | Zaten kötü OCR metin katmanı olan bir PDF (Google Books vb.) |
- [ ] | `two-column-academic` | arXiv makalesi |
- [ ] | `book-with-images` | Görsel ağırlıklı bir kitap/rehber |
- [ ] | `book-with-tables` | Tablo içeren teknik/akademik bir doküman |
- [ ] | `book-with-footnotes` | Dipnotlu akademik bir kitap |
- [ ] | `technical-with-code` | Açık kaynak bir programlama kitabı (ör. `progit`) |
- [ ] | `turkish` | Türkçe bir e-kitap |
- [ ] | `english` | İngilizce bir e-kitap |
- [ ] | `multilingual` | Birden fazla dil içeren bir doküman |
- [ ] | `complex-headings` | Çok seviyeli başlık hiyerarşisi olan bir kitap |
- [ ] | `lists-and-quotes` | Liste/alıntı ağırlıklı bir kitap |
- [ ] | `unusual-fonts` | Özel/subset font kullanan bir PDF |
- [ ] | `mathematical` (unsupported) | `metadata.json`'da `"unsupported": true` -- skora dahil edilmez, yalnızca raporlanır |
