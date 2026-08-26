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
→ 77.6 (görsel konumlandırma/interleaving + boyut filtresi düzeltmesi, iki golden `expected_image_count` hatası giderildi — images %91.6→%91.8)
→ 78.9 (madde 1: font-boyutu/kalınlık sinyali `complex-headings`'in sahte `<h2>`'lerini düzeltti — o kitap 80.7→85.8, `scanned_002`'de küçük/kabul edilen bir yan etki dışında tüm kitaplarda iyileşme — aşağıya bkz.)
→ 78.9 (madde 3: bölüm tespiti fallback'i eklendi — skor KASITLI OLARAK değişmedi: `eval/`'daki hiçbir dosya `detect_chapters`/`analyze_pdf` çağırmıyor, `structure`'ın `chapter_recall`'ü üretilen EPUB'ın KENDİ TOC'undan geliyor (`config["chapters"]`'a bağlı, `plan_conversion`/`assemble_epub`'ın işi) — `detect_chapters` yalnızca `/analyze` önizleme uç noktasını besliyor, dönüşüm pipeline'ına hiç girmiyor. Doğrulama bu yüzden eval yerine 5 golden `expected_chapters` kitabı üzerinde doğrudan `detect_chapters(doc)` çağrılarak elle yapıldı, aşağıya bkz.)
→ 79.0 (N-sütun okuma sırası bug'ı düzeltildi — `_split_into_reading_order_segments` artık gerçekten 3+ sütunlu sayfaları doğru sıralıyor, eskiden yalnızca sayfayı orta çizgiden ikiye ayırıp her yarının kendi içindeki alt-sütunları karıştırıyordu. Küçük bir iyileşme çünkü golden setteki çoğu sayfa hâlâ tek/iki sütunlu, aşağıya bkz.)
→ 79.9 (kenar payı devam-satırı bug'ı düzeltildi — agresif kalibre edilmiş bir üst kenar payı şeridine düşen, bir cümlenin satır sarmasıyla oluşan paragraf kuyrukları artık gerçek koşu başlığı/sayfa no gibi silinmiyor. `book-with-images_966108`'de tek başına +14.6 puan/kitap; aşağıya bkz.)
→ 82.9 (eval'ın kendi `duplicates.py` yanlış-pozitifi düzeltildi — sayfa oranına göre gerçek sızıntı/zararsız tekrar ayrımı eklendi, `converter.py`'ye dokunulmadı. `book-with-images_966108`'de tek başına +3.8 puan/kitap; aşağıya bkz.)
→ 83.5 (eval'ın kendi apostrof+boşluk normalizasyon eksikliği düzeltildi — Türkçe özel-ad+ek apostrofundaki PDF-çıkarım kaynaklı sahte boşluk artık `normalize_phrase`'de siliniyor, `converter.py`'ye dokunulmadı. `two-column-academic_farkindalik-gelistirme-programi`'de tek başına +10.9 puan/kitap; aşağıya bkz.)
→ 83.3 (eval'ın kendi `images` metriği artık benzersiz dosya sayısını ölçüyor, `<img>` occurrence sayısını değil — genel skor -0.2 net düştü ama metrik artık gerçeği ölçüyor, birkaç kitapta gizli kalmış boşluklar görünür oldu; `converter.py`'ye dokunulmadı, aşağıya bkz.)
→ **86.3 (`unsupported: true` bayrağı artık gerçekten skor/gate'e dahil edilmiyor — README'nin belgelediği niyet buydu ama hiç uygulanmamıştı, `mathematical_singular-integrals` artık overall ortalamayı düşürmüyor/gate uyarısı tetiklemiyor. `converter.py`'ye dokunulmadı, aşağıya bkz.)**

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

- ~~Madde 1: `complex-headings_tu-rkiye-sigorta-klavuz` paragraf-sayısı düşüklüğü — font-boyutu sinyali~~ —
  2026-08-25/26'da düzeltildi. Kullanıcı "Font-boyutu sinyali (madde 1 + bölüm tespiti
  birlikte)" seçeneğini seçti. Gerçek kitap incelemesiyle doğrulandı: font boyutu (20pt
  kalın) vs gövde (12pt normal) AYNI metin ("Kalan Limit") farklı yerlerde farklı
  roller (gerçek başlık / sahte başlık) oynasa bile temiz bir ayrım sağlıyor. Yeni
  `HEADING_FONT_SIZE_RATIO=1.15` + kalınlık bayrağı kontrolü (`_is_bold_span`,
  `_looks_like_heading_font`), mevcut interleaved-sayfa pipeline'ına eklendi (eski düz/OCR
  pipeline'a dokunulmadı). Sonuç: kitap skoru 80.7→85.8, `structure` %44.8→%72.4. Fast
  eval (16 kitap): 77.6→78.9, `scanned_002` hariç TÜM kitaplarda iyileşme (`scanned_002`
  82.9→81.4, kitabın önceden bilinen bozuk gömülü tarayıcı-OCR font katmanının kabul
  edilen bir yan etkisi — ayrı bir veri kalitesi sorunu, genel bir regresyon riski değil).
  Detay: `TAMAMLANANLAR.md`.
- ~~Madde 3: Bölüm tespiti (chapter detection) fallback'i~~ — 2026-08-26'da eklendi.
  Kullanıcı önce "Evet, örneklem sayfa OCR'la dene" sonra (sparse-sample recall düşük
  çıkınca) "Daha yoğun örneklem (~5 sayfada bir)" seçeneklerini seçti. `detect_chapters`
  yalnızca `/analyze` önizleme uç noktasını besliyor (dönüşüm pipeline'ına hiç girmiyor,
  bkz. yukarıdaki skor notu) — bu yüzden 5 golden `expected_chapters` kitabı üzerinde
  doğrudan `detect_chapters(doc)` çağrılarak elle doğrulandı: `scanned_002` artık 8/8
  gerçek bölümü doğru buluyor (önceden: kitabın kendi bozuk TOC'u yüzünden tek bir
  yanlış "bölüm"), `book-with-images_ankaranin-trekking-rotalari` 7 gerçek bölümün
  tamamını (+2 makul fazladan aday) buluyor, `technical-with-code_functional-programing`
  7 gerçek bölümün tamamını (+2 ek bulunan gerçek ek/appendix) buluyor,
  `turkish_bilimsel-makale-nasil-yazilir` 2 beklenenden 1'ini buluyor (önceden: 31 sahte
  dekoratif-ayraç "bölümü"), `scanned_001` artık boş liste dönüyor (önceden: kitapta hiç
  gerçek bölüm yokken 40 rastgele cümleyi "bölüm" sayıyordu — expected de zaten tek bir
  `'Sabrina'` etiketi, yani gerçek bir alt-yapı yok, dürüst boş liste doğru davranış).
  Uygulama sırasında 5 ayrı bug bulunup düzeltildi: (1) pt (gömülü-metin punto) ve px
  (OCR satır-yüksekliği) birimli adayların TEK bir havuzda kıyaslanması — bir OCR
  yanlış-okuması (190px) 8 doğru pt-bazlı bölümü tavanın altına düşürüp eliyordu; (2)
  kitabın kendi başlığının kapak sayfasında büyük puntoyla tekrarı gerçek bir bölüm
  başlığıyla ayırt edilemiyordu — `_matches_known_title_or_author` eklendi (Türkçe
  İ/ı/Ü aksan kaybı normalizasyonuyla, `_fold_turkish_for_loose_match`); (3) düz/tek-
  seviyeli ya da tarayıcı-üretimi sayfa-başına-bookmark gömülü outline'lara körü körüne
  güvenilmesi (`technical-with-code_functional-programing`: 148 ham girdi/7 gerçek bölüm,
  `scanned_002`: 188 girdi/188 sayfa) — `_toc_chapters_look_plausible` (sayfa/bölüm oranı
  eşiği) eklendi; (4) gövde-punto tabanı tespit edilemeyince (`body_font_size=None`)
  font-boyutu sezgisinin "her şey başlık" varsayımına düşmesi (`scanned_001`'de HER
  rastgele cümleyi bölüm sayıyordu) — taban yoksa gömülü-metin yolu artık hiç aday
  üretmiyor; (5) dekoratif noktalama ayraçlarının ("◆ ◆ ◆") başlık şekli testini geçmesi
  — metinde en az bir harf zorunluluğu eklendi. Ayrıca numaralandırma deseni ("Chapter
  N.", "Appendix A.") en büyük punto katmanındaysa boyut-katmanı sezgisinden daha
  güvenilir bir sinyal sayılıyor (düz outline'lı kitaplarda alt-başlıklar bölümlerle aynı
  punto/kalınlıkta basılı olabildiğinden), ama numaralı adaylar genel tavandan belirgin
  düşükse (ör. bir gezi rehberinin numaralı yürüyüş-rotası alt-maddeleri) bu sinyale
  güvenilmiyor. 16 yeni birim/entegrasyon testi eklendi (`test_converter.py`), suite
  71/71 yeşil. Detay: `TAMAMLANANLAR.md`.
- ~~N-sütun okuma sırası bug'ı (NOTES.md'de ayrı bir "Sorunlar" maddesiydi, madde 2'nin
  manuel doğrulaması sırasında bulunmuştu)~~ — 2026-08-26'da düzeltildi.
  `_split_into_reading_order_segments`, gerçekten çok sütunlu (3+, dergi/rehber tarzı)
  sayfalarda sayfayı yalnızca orta çizgiden ikiye ayırıp her yarının kendi içindeki
  alt-sütunları karıştırıyordu (kanıt: `book-with-images_ankaranin-trekking-rotalari`
  sayfa 5, 4 sütunlu). Yeni `_detect_column_bands` blokları x0 yakınlığına göre bant'lara
  ayırıyor (N sütuna genelleşiyor). Uygulama sırasında manuel doğrulamayla 3 ayrı
  yanlış-pozitif riski bulunup düzeltildi (bir görsel altyazısının iki sütunu köprülemesi,
  paragraf ilk-satır girintisinin sahte 2-sütun sayılması, harita etiketlerinin sahte
  sütun sayılması). 3 yeni regresyon testi, suite 71→74 yeşil. Fast eval: 78.9→79.0,
  hiçbir kitapta gerileme yok; hedef kitap tam eval'da 34.9→35.2. Detay: `TAMAMLANANLAR.md`.
- ~~Kenar payı devam-satırı bug'ı (en düşük skorlu kitaba bakılırken bulundu, `book-with-images_966108`)~~ —
  2026-08-26'da düzeltildi. `--book` diagnostic'inin tek bir `Missing phrases` maddesinden
  (`"ASTM D 7012 standartlarına uygun tek eksenli sıkışma dayanımı"`) izlenen kök neden:
  agresif kalibre edilmiş (%15) bir üst kenar payı şeridinde kalan KISA bloklar, hemen
  üstündeki (şerit dışına taşan) bir paragrafın satır-sarması devamı olsalar bile gerçek
  koşu başlığı/sayfa no gibi sessizce siliniyordu. Yeni `_looks_like_paragraph_continuation`,
  silmeden önce hemen üstte noktalamayla BİTMEYEN bir blok olup olmadığına bakıyor.
  Tek bir cümleyle sınırlı değildi -- `text_completeness` %66.7→%100, kitap skoru
  61.2→75.8 (+14.6). Fast eval: 79.0→79.9, hiçbir kitapta gerileme yok. 2 yeni regresyon
  testi, suite 74→76 yeşil. Detay: `TAMAMLANANLAR.md`.
- ~~`eval/metrics/duplicates.py` yanlış-pozitifi (NOTES.md'de ayrı bir "Sorunlar"
  maddesiydi, kenar payı bug'ının manuel doğrulamasında bulunmuştu)~~ — 2026-08-26'da
  düzeltildi. `book-with-images_966108`'deki 30+ neredeyse özdeş gerilme-deformasyon
  grafiğinin meşru şekilde tekrar eden eksen/lejant etiketleri (549 occurrence, 43 farklı
  metin) `block_penalty`'yi tavana (1.0) vurduruyordu — pipeline'da düzeltilecek bir şey
  yoktu, saf eval metrik bug'ı. Fix: `evaluate_duplicates` artık `total_pages` alıp her
  tekrar eden bloğun `count/total_pages` oranına bakıyor, yalnızca sayfaların yarısından
  fazlasında görülenler (gerçek koşu başlığı/sayfa no deseni) skoru etkiliyor — bu kitapta
  en yüksek oran bile %45'te kalıyor (67/149 sayfa), hiçbiri eşiği geçmiyor. Test:
  `book-with-images_966108` 75.8→79.6, fast eval 79.9→82.9, hiçbir kitapta gerileme yok.
  Detay: `TAMAMLANANLAR.md`.
- ~~Apostrof+boşluk normalizasyon eksikliği (NOTES.md'de ayrı bir "Sorunlar" maddesiydi,
  görsel boyut-filtresi çalışması sırasında rastlantıyla bulunmuştu)~~ — 2026-08-26'da
  düzeltildi. `two-column-academic_farkindalik-gelistirme-programi`'de bir must_include
  ifadesi sürekli "Missing phrase" düşüyordu: ham PDF'te `"UG' nin"` (Türkçe özel-ad+ek
  apostrofunda PDF-çıkarım kaynaklı sahte boşluk) çıkıyor, golden ifade boşluksuz
  `"UG'nin"` bekliyordu — `_QUOTE_VARIANTS` tırnak tipini düzeltiyordu ama boşluğu değil.
  Fix: `eval/text_utils.py`'deki `normalize_phrase`'e harf-apostrof-boşluk-harf dizisini
  boşluksuza indirgeyen bir regex eklendi. Test: hedef kitap 86.3→97.2, fast eval
  82.9→83.5, diğer 15 kitapta değişiklik yok. Detay: `TAMAMLANANLAR.md`.
- ~~`eval/metrics/images.py`'nin occurrence/benzersiz-dosya karışıklığı (madde 2'nin
  cross-page dedup alt-adımı sırasında bulunmuştu, NOTES.md'de ayrı bir "Sorunlar"
  maddesiydi)~~ — 2026-08-26'da düzeltildi. Golden `expected_image_count` benzersiz
  xref/dosya sayısından tahmin ediliyor ama metrik `<img>` etiketi OCCURRENCE sayısıyla
  karşılaştırıyordu. Fix: `evaluate_images` artık `EpubContent.total_image_items`
  (benzersiz dosya, kapak hariç) alıp golden karşılaştırmasında bunu kullanıyor. Sonuç
  KASITLI OLARAK karışık: fast eval overall -0.2 net düştü (`book-with-tables_table`
  72.6→69.2, `scanned_002` 87.2→85.5) çünkü metrik artık bazı kitaplarda daha önce
  occurrence-sayımının maskelediği gerçek benzersiz-görsel boşluklarını gösteriyor —
  bu bir gerileme değil, metriğin daha doğru ölçmesinin sonucu (`book-with-tables_table`
  zaten ayrı bir NOTES.md maddesinde golden-veri belirsizliği olarak takipte).
  Detay: `TAMAMLANANLAR.md`.
- ~~`unsupported: true` bayrağının skor/gate'i hiç etkilememesi (eski madde 4'ün yan
  bulgusu, NOTES.md'de ayrı bir "Sorunlar" maddesiydi)~~ — 2026-08-26'da düzeltildi.
  `eval/README.md` "skora dahil edilmez, yalnızca raporlanır" diyordu ama
  `evaluate.py`/`scoring.py`/`run.py`'de bu alana hiç referans yoktu — belgelenen niyet
  netti, eksik olan uygulamaydı. Fix: `BookResult.unsupported` eklendi, `report.py`'nin
  `build_run_summary`'si overall skoru/metric ortalamalarını/"Dikkat gerektiren
  kitaplar" listesini yalnızca desteklenen kitaplardan hesaplıyor; unsupported kitap
  yine de per-kitap satırında/JSON'da görünüyor (raporlanıyor, gate'e girmiyor). Test:
  fast eval (`mathematical_singular-integrals` dahil) 83.3→86.3, "Dikkat gerektiren
  kitaplar" artık boş. Detay: `TAMAMLANANLAR.md`.

## Diğer (bu roadmap'in kapsamı dışı, ayrı konular)

`NOTES.md`'deki diğer maddeler (rate limiting, `process_chunk` egress israfı,
`ConvertJobStatus.PROCESSING`, ödeme/webhook konuları vb.) bu dönüşüm-kalitesi
çalışmasıyla ilgisiz, ayrı takip ediliyor.
