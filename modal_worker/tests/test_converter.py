import io
import zipfile

import pymupdf
import pytest

from converter import (
    CHUNK_PAGE_SIZE,
    HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    ConversionError,
    analyze_pdf,
    clean_text,
    convert_pdf_to_epub,
    detect_chapters,
    detect_title_author,
    extract_page_text,
    plan_conversion,
    process_page_range,
    text_to_html_blocks,
)
from converter import (
    _detect_chapter_candidate_from_dict_page,
    _filter_chapter_candidates,
    _is_chapter_heading_shaped,
    _is_mostly_uppercase,
    _matches_known_title_or_author,
    _toc_chapters_look_plausible,
)


def test_clean_text_merges_hyphenated_linebreaks():
    assert clean_text("kita-\nplar") == "kitaplar"


def test_clean_text_collapses_single_linebreaks_but_keeps_paragraphs():
    text = "birinci satir\nikinci satir\n\nyeni paragraf"
    assert clean_text(text) == "birinci satir ikinci satir\n\nyeni paragraf"


def test_text_to_html_blocks_wraps_paragraphs():
    html = text_to_html_blocks("Bu bir paragraftir ve yeterince uzundur.")
    assert html.startswith("<p>")
    assert html.endswith("</p>")


def test_text_to_html_blocks_still_detects_real_short_headings():
    """Sıkılaştırılmış h2 sezgiseli gerçek kısa alt başlıkları hâlâ yakalamalı --
    aşağıdaki regresyon testlerinin (denklem/atıf/eksen-etiketi reddi) yanlışlıkla
    TÜM kısa satırları <p>'ye düşürmediğini doğrular."""
    assert text_to_html_blocks("İntro") == "<h2>İntro</h2>"
    assert text_to_html_blocks("4.1 Kayaların Mineralojik ve Petrografik Özellikleri") == (
        "<h2>4.1 Kayaların Mineralojik ve Petrografik Özellikleri</h2>"
    )


def test_text_to_html_blocks_rejects_equation_fragments_as_headings():
    """Denklem parçaları (Yunan harfi/matematiksel Unicode/Symbol-font kaçağı) kısa
    ve noktalamasız oldukları için eski sezgisel bunları <h2> sayıyordu -- regresyon
    testi: book-with-images_966108'de 721 sahte h2'nin ~154'ü bu kategoriydi (bkz.
    NOTES.md/ROADMAP.md madde 1)."""
    assert text_to_html_blocks("σ , MPa") == "<p>σ , MPa</p>"
    assert text_to_html_blocks("𝜏𝑝= 𝐶0(1 −𝑒−𝑏𝜎𝑛) + 𝜎𝑛𝑡𝑎𝑛𝜙𝑟 (3.7)") == (
        "<p>𝜏𝑝= 𝐶0(1 −𝑒−𝑏𝜎𝑛) + 𝜎𝑛𝑡𝑎𝑛𝜙𝑟 (3.7)</p>"
    )


def test_text_to_html_blocks_rejects_citation_fragments_and_toc_leaders_as_headings():
    assert text_to_html_blocks("JRC değerleri (Vallejo ve Ferrer 2002'den)") == (
        "<p>JRC değerleri (Vallejo ve Ferrer 2002&#x27;den)</p>"
    )
    assert text_to_html_blocks("ÖZGEÇMİŞ.......... 139") == "<p>ÖZGEÇMİŞ.......... 139</p>"


def test_text_to_html_blocks_rejects_axis_labels_as_headings():
    assert text_to_html_blocks("a b") == "<p>a b</p>"
    assert text_to_html_blocks("0 100 200 300 400 500") == "<p>0 100 200 300 400 500</p>"


def test_convert_pdf_to_epub_produces_valid_epub_zip(sample_pdf_bytes):
    config = {"title": "Test Kitap", "author": "Test Yazar", "language": "tr"}
    result = convert_pdf_to_epub(sample_pdf_bytes, config)

    assert isinstance(result, bytes)
    assert result[:4] == b"PK\x03\x04"  # EPUB bir ZIP arşividir


def test_convert_pdf_to_epub_raises_on_invalid_pdf(corrupt_pdf_bytes):
    with pytest.raises(ConversionError):
        convert_pdf_to_epub(corrupt_pdf_bytes, {"title": "X"})


def test_convert_pdf_to_epub_falls_back_to_page_image_when_no_text_found(scanned_pdf_bytes):
    """Taranmış/görsel sayfalarda metin+OCR başarısız olsa da sayfa sessizce atlanmamalı.

    Regresyon testi: eskiden bu durumda sayfa tamamen düşürülüyor, sonuçta
    içeriksiz (yalnızca başlık) bir EPUB üretiliyordu.
    """
    config = {"title": "Taranmis Kitap"}
    result = convert_pdf_to_epub(scanned_pdf_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if name.endswith(".png") or name.endswith(".jpg")]
        assert image_entries, "Metni çıkarılamayan sayfa görsel olarak eklenmeli, atlanmamalı"


def test_convert_pdf_to_epub_extracts_embedded_image_from_text_page(pdf_with_embedded_image_bytes):
    """Metinle karışık, normal bir metin sayfasındaki gömülü görsel artık
    çıkarılıp EPUB'a ekleniyor olmalı (hem metin hem görsel korunmalı).

    Regresyon testi: eskiden `_extract_text_blocks` görsel blokları
    (`block[6] != 0`) atlıyordu ve metin yolunda hiç görsel çıkarımı
    yapılmıyordu — görseller yalnızca `diagram_pages`/tam-sayfa-görsel
    fallback'inde korunuyordu (bkz. NOTES.md)."""
    config = {"title": "Gorselli Kitap"}
    result = convert_pdf_to_epub(pdf_with_embedded_image_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if "_img_" in name]
        assert image_entries, "Metinle karışık gömülü görsel çıkarılıp eklenmeli"
        assert image_entries[0].endswith(".png")

        chapter_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        assert "gomulu bir gorsel var" in chapter_html.lower(), "Görsel eklenirken sayfanın metni kaybolmamalı"
        assert "<img" in chapter_html


def test_convert_pdf_to_epub_skips_unplaced_image_resource(pdf_with_unplaced_image_resource_bytes):
    """Bir sayfanın kaynak sözlüğünde referans edilen ama o sayfada hiç çizilmeyen bir
    görsel `<img>` olarak eklenmemeli -- yalnızca gerçekten çizilmiş görseller (bu
    fixture'da 1. sayfadaki) EPUB'a girmeli.

    Regresyon testi: `extract_embedded_page_images`, `page.get_images(full=True)`'in
    döndürdüğü HER xref'i (sayfada gerçekten çizilip çizilmediğine bakmadan) çıkarıyordu
    -- gerçek PDF'lerde (bkz. `book-with-images_966108` sayfa 17, xref=2) sayfada hiç
    görünmeyen bir görsel için sahte bir `<img>` üretilmesine yol açıyordu."""
    config = {"title": "Kullanilmayan Kaynakli Kitap"}
    result = convert_pdf_to_epub(pdf_with_unplaced_image_resource_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if "_img_" in name]
        assert len(image_entries) == 1, f"Yalnızca gerçekten çizilmiş görsel eklenmeli, bulunanlar: {image_entries}"

        chap2_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        assert chap2_html.count("<img") == 1, "Kullanılmayan kaynak <img> olarak sızmamalı"


def test_convert_pdf_to_epub_dedups_identical_image_across_pages(pdf_with_duplicate_image_across_pages_bytes):
    """Aynı görsel (aynı bayt içeriği) birden fazla sayfada tekrarsa EPUB'a yalnızca
    BİR kopya eklenmeli -- diğer sayfalardaki `<img>` referansları o tek kopyaya
    yönlendirilmeli.

    Regresyon testi: `assemble_epub`'daki görsel ekleme döngüsü, sayfa-içi dedup'ı
    olan (`extract_embedded_page_images`'teki `seen_xrefs`) ama sayfa-AŞIRI dedup'ı
    olmayan bir noktaydı -- aynı görsel farklı sayfalarda (dosya adı sayfa numarasını
    içerdiğinden) her tekrarda ayrı bir dosya olarak ekleniyordu (bkz. NOTES.md/
    ROADMAP.md Faz 2'den açık kalan sınırlama)."""
    config = {"title": "Tekrarli Gorselli Kitap"}
    result = convert_pdf_to_epub(pdf_with_duplicate_image_across_pages_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if "_img_" in name]
        assert len(image_entries) == 1, f"Aynı görsel tek bir dosyaya dedup edilmeli, bulunanlar: {image_entries}"

        chapter_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        assert chapter_html.count("<img") == 2, "İki sayfa da kendi <img> referansını korumalı"
        canonical_name = image_entries[0].split("/")[-1]
        assert chapter_html.count(canonical_name) == 2, "Her iki referans da aynı (tek) dosyayı göstermeli"


def test_convert_pdf_to_epub_interleaves_embedded_image_between_paragraphs(pdf_with_image_between_paragraphs_bytes):
    """Gömülü görsel artık sayfanın SONUNA değil, PDF'teki gerçek konumuna
    (iki paragraf arasına) yerleştirilmeli.

    Regresyon testi: eskiden `process_page`, tüm sayfa metnini tek bir
    `text_to_html_blocks` çağrısıyla HTML'e çevirip gömülü görselleri ayrı
    bir döngüyle en SONA ekliyordu (bkz. ROADMAP.md madde 2, "konumlandırma
    yaklaşık" sınırlaması) -- bu fixture'da görsel iki paragraf arasında
    olduğundan, eski davranışta ikinci paragraftan SONRA çıkardı."""
    config = {"title": "Aralarda Gorselli Kitap"}
    result = convert_pdf_to_epub(pdf_with_image_between_paragraphs_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        chapter_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        first_idx = chapter_html.lower().index("once gelir")
        img_idx = chapter_html.index("<img")
        second_idx = chapter_html.lower().index("sonra gelir")
        assert first_idx < img_idx < second_idx, "Görsel iki paragraf arasına yerleştirilmeli, sayfa sonuna değil"


def test_convert_pdf_to_epub_keeps_small_raw_but_large_display_image(pdf_with_small_raw_but_large_display_image_bytes):
    """Ham piksel boyutu küçük olsa da sayfada büyük gösterilen (yukarı
    ölçeklenen) bir görsel tutulmalı -- boyut filtresi artık ham piksel
    boyutuna değil, sayfadaki GÖRÜNEN (rect) boyutuna bakıyor.

    Regresyon testi: eski `MIN_EMBEDDED_IMAGE_DIMENSION=40px` ham-piksel
    filtresi bu 20x20px görseli (100x100pt olarak gösterilse bile) atlardı."""
    config = {"title": "Kucuk Ham Buyuk Gosterim"}
    result = convert_pdf_to_epub(pdf_with_small_raw_but_large_display_image_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if "_img_" in name]
        assert image_entries, "Ham piksel boyutu küçük olsa da sayfada büyük gösterilen görsel tutulmalı"


def test_convert_pdf_to_epub_skips_large_raw_but_tiny_display_image(pdf_with_large_raw_but_tiny_display_image_bytes):
    """Ham piksel boyutu büyük olsa da sayfada küçük (ikon boyutunda)
    gösterilen bir görsel atlanmalı -- boyut filtresi artık sayfadaki
    GÖRÜNEN (rect) boyutuna bakıyor, ham piksel boyutuna değil.

    Regresyon testi: eski ham-piksel filtresi bu 500x500px görseli (10x10pt
    gibi ikon boyutunda gösterilse bile) yanlışlıkla tutardı."""
    config = {"title": "Buyuk Ham Kucuk Gosterim"}
    result = convert_pdf_to_epub(pdf_with_large_raw_but_tiny_display_image_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if "_img_" in name]
        assert not image_entries, "Sayfada ikon boyutunda gösterilen görsel, ham piksel boyutu büyük olsa da atlanmalı"


def test_convert_pdf_to_epub_ocr_recovers_text_from_scanned_page(ocr_scanned_page_bytes):
    """Metin katmanı olmayan ama görselde okunabilir metin bulunan bir sayfada,
    OCR kuruluysa gerçek metin çıkarılmalı — sayfa sessizce görsele düşmemeli.

    Ayrıca (regresyon): taranmış bir sayfanın PDF içindeki "gömülü görseli"
    genelde taramanın kendisi (tüm sayfayı kaplayan tek bir raster) olduğundan,
    gömülü görsel çıkarımı (`extract_embedded_page_images`) bu sayfada
    ÇALIŞMAMALI — yoksa OCR'lanan metnin altına aynı sayfanın gereksiz bir
    kopyası eklenir."""
    config = {"title": "OCR Kitap"}
    result = convert_pdf_to_epub(ocr_scanned_page_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        chapter_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        assert "hello" in chapter_html.lower(), "OCR ile çıkarılan metin bölüm HTML'inde görünmeli"

        image_entries = [name for name in archive.namelist() if name.startswith("EPUB/images/")]
        assert not image_entries, "Gerçek OCR metni bulunduğunda sayfa görsele/gömülü-görsele düşmemeli"


def test_detect_chapters_reads_embedded_toc(pdf_with_toc_bytes):
    doc = pymupdf.open(stream=pdf_with_toc_bytes, filetype="pdf")
    chapters = detect_chapters(doc)
    doc.close()

    # TOC sayfa 2'den basliyor, sayfa 1 kaybolmasin diye basa bir giris bolumu eklenmeli.
    assert chapters == [
        {"start_page": 1, "title": "Giriş"},
        {"start_page": 2, "title": "Birinci Bolum"},
        {"start_page": 4, "title": "Ikinci Bolum"},
    ]


def test_detect_chapters_returns_empty_without_toc(sample_pdf_bytes):
    doc = pymupdf.open(stream=sample_pdf_bytes, filetype="pdf")
    chapters = detect_chapters(doc)
    doc.close()
    assert chapters == []


def test_detect_chapters_falls_back_when_toc_looks_like_per_page_bookmarks():
    """Bazı taranmış PDF'lerin gömülü outline'ı gerçek bölüm yapısını değil,
    tarayıcı yazılımının her sayfa için ürettiği bir dosya-adı bookmark'ını
    taşıyor (gerçek bir örnekte: scanned_002, 188 sayfa için 188 outline
    girdisi). Böyle bir TOC'a körü körüne güvenmek yerine, sayfa/bölüm
    oranı gerçekçi değilse TOC'un tamamı reddedilip fallback'e düşülmeli."""
    doc = pymupdf.open()
    for i in range(1, 11):
        doc.new_page()
    # 10 sayfalık bir belgede 8 "bölüm" -- 1.25 sayfa/bölüm, gerçekçi değil.
    doc.set_toc([[1, f"Sayfa - {i:03d}", i] for i in range(1, 9)])
    chapters = detect_chapters(doc)
    doc.close()
    assert chapters == []


def test_toc_chapters_look_plausible_rejects_dense_per_page_toc():
    assert _toc_chapters_look_plausible(188, 188) is False
    assert _toc_chapters_look_plausible(148, 261) is False  # düz/tek-seviyeli outline, alt-başlıklar dahil


def test_toc_chapters_look_plausible_accepts_short_paper_toc():
    assert _toc_chapters_look_plausible(5, 11) is True
    assert _toc_chapters_look_plausible(7, 15) is True


def test_toc_chapters_look_plausible_accepts_single_entry():
    assert _toc_chapters_look_plausible(1, 500) is True


def test_filter_chapter_candidates_outlier_does_not_dominate_tier():
    """gerçek bir örnekte (scanned_002, sayfa 1'in OCR yanlış okuması): bir
    kapak illüstrasyonunun OCR yanlış okuması (190px, gövde/başlık
    boyutlarından KAT KAT büyük) tek başına tavanı yükseltip AYNI stildeki
    8 gerçek bölüm başlığını (17-23px, tavanın %90'ının altında kalarak)
    eleyebiliyordu. Medyan tabanlı uç-değer tavanı bu tek seferlik
    outlier'ı safdışı bırakmalı."""
    candidates = [
        (1, "KAPAK YANLIŞ OKUMASI", 190.0),
        (8, "GERÇEK BÖLÜM 1", 17.0),
        (10, "GERÇEK BÖLÜM 2", 17.0),
        (40, "GERÇEK BÖLÜM 3", 17.0),
        (77, "GERÇEK BÖLÜM 4", 17.0),
    ]
    chapters = _filter_chapter_candidates(candidates, tier_ratio=0.9)
    titles = [c["title"] for c in chapters]
    assert "KAPAK YANLIŞ OKUMASI" not in titles
    assert "GERÇEK BÖLÜM 1" in titles
    assert "GERÇEK BÖLÜM 2" in titles
    assert "GERÇEK BÖLÜM 3" in titles
    assert "GERÇEK BÖLÜM 4" in titles


def test_filter_chapter_candidates_uses_numbering_when_it_matches_top_tier():
    """gerçek bir örnekte (technical-with-code_functional-programing): düz/
    tek-seviyeli bir outline yüzünden gömülü aday havuzu, gerçek bölümlerle
    AYNI punto/kalınlıktaki onlarca alt-başlıkla dolu. "Chapter N." gibi
    açık bir numaralandırma deseni VE bu adayların en büyük punto
    katmanında olması, saf boyut sezgisinden daha güvenilir bir sinyal."""
    candidates = [
        (10, "Credits", 28.8),
        (12, "About the Author", 28.8),
        (43, "Chapter 1. The Powers", 28.8),
        (58, "Chapter 2. Fundamentals", 28.8),
        (92, "Chapter 3. Setting Up", 28.8),
        (100, "Category theory in a nutshell", 23.8),
    ]
    chapters = _filter_chapter_candidates(candidates, tier_ratio=0.9)
    titles = [c["title"] for c in chapters]
    assert titles == ["Chapter 1. The Powers", "Chapter 2. Fundamentals", "Chapter 3. Setting Up"]


def test_filter_chapter_candidates_ignores_numbering_when_not_at_top_tier():
    """gerçek bir örnekte (book-with-images_ankaranin-trekking-rotalari):
    numaralandırılmış adaylar ("17. Çamlıdere-Çamlıdere") aslında yürüyüş
    rotası alt-maddeleri, küçük puntoda; gerçek bölüm başlıkları numarasız
    ama daha büyük puntoda. Numaralandırma sinyaline, yalnızca genel tavana
    yakın bir katmanda olduğunda güvenilmeli."""
    candidates = [
        (6, "ANADOLU'NUN KAVŞAK NOKTASI", 15.0),
        (13, "YEŞİL SIĞINAK", 15.0),
        (17, "2) Alakoç Köyü-Alakoç Yaylası", 11.0),
        (32, "17. Çamlıdere-Çamlıdere", 11.0),
    ]
    chapters = _filter_chapter_candidates(candidates, tier_ratio=0.9)
    titles = [c["title"] for c in chapters]
    assert titles == ["ANADOLU'NUN KAVŞAK NOKTASI", "YEŞİL SIĞINAK"]


def test_matches_known_title_or_author_handles_turkish_diacritic_loss():
    """gerçek bir örnekte (scanned_002): kapak sayfasındaki başlık tekrarı
    ("BiR GUN") gömülü fontta Türkçe aksanları (İ, Ü) kaybetmiş şekilde
    çıkarılmıştı -- gerçek yazar/başlıkla ("BİR GÜN") harfiyen karşılaştırma
    (hatta standart .casefold() ile bile) eşleşmiyordu."""
    assert _matches_known_title_or_author("BiR GUN", "YVANWVMYVA DINIS", "BİR GÜN") is True


def test_matches_known_title_or_author_rejects_unrelated_text():
    assert _matches_known_title_or_author("ŞEYTAN GÖRÜNÜR", "YVANWVMYVA DINIS", "BİR GÜN") is False


def test_is_chapter_heading_shaped_rejects_punctuation_only():
    """gerçek bir örnekte (turkish_bilimsel-makale-nasil-yazilir): dekoratif
    bir bölüm-ayracı ("◆ ◆ ◆") 3 "kelime" olarak sayılıp başlık şekli
    testini geçiyor, sayfa başına tekrarlanarak onlarca sahte bölüm
    üretiyordu."""
    assert _is_chapter_heading_shaped("◆ ◆ ◆") is False
    assert _is_chapter_heading_shaped("Gerçek Bir Başlık") is True


def test_is_mostly_uppercase():
    assert _is_mostly_uppercase("SALI: EGER TELEFONLAR") is True
    assert _is_mostly_uppercase("şahane görünüyordu.") is False


def test_detect_chapter_candidate_from_dict_page_requires_body_font_size():
    """gerçek bir örnekte (scanned_001): belgenin tamamında güvenilir bir
    gövde-punto tabanı bulunamayınca (`body_font_size=None`), font-boyutu
    sezgisi "her şey başlık" varsayımına düşüp kitaptaki HER rastgele
    cümleyi bölüm başlığı sayıyordu (40'tan fazla sahte bölüm). Gövde-punto
    tabanı yoksa gömülü-metin yolu hiç aday üretmemeli."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Sıradan bir gövde cümlesi burada.", fontsize=12)
    candidate = _detect_chapter_candidate_from_dict_page(page, None)
    doc.close()
    assert candidate is None


def test_detect_chapters_uses_font_size_fallback_without_toc():
    """TOC yokken, gömülü metindeki font-boyutu/kalınlık farkı gerçek bir
    bölüm başlığını gövde metninden ayırt edebilmeli."""
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), "Bu sayfadaki metin govde paragrafidir, yeterince uzundur.", fontsize=12)
    heading_page = doc.new_page()
    heading_page.insert_text((72, 100), "Gercek Bolum Basligi", fontsize=24)
    heading_page.insert_text((72, 200), "Bu bolumun govde metni burada devam ediyor.", fontsize=12)
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), "Yine sayfadaki metin govde paragrafidir, yeterince uzundur.", fontsize=12)

    chapters = detect_chapters(doc)
    doc.close()

    titles = [c["title"] for c in chapters]
    assert "Gercek Bolum Basligi" in titles


def test_detect_title_author_prefers_metadata(pdf_with_metadata_bytes):
    doc = pymupdf.open(stream=pdf_with_metadata_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Metadata Basligi"
    assert author == "Metadata Yazari"


def test_detect_title_author_falls_back_to_cover_text(pdf_with_cover_text_bytes):
    doc = pymupdf.open(stream=pdf_with_cover_text_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Buyuk Baslik"
    assert author == "Yazar Adi"


def test_detect_title_author_returns_none_when_nothing_found(blank_pdf_bytes):
    doc = pymupdf.open(stream=blank_pdf_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title is None
    assert author is None


def test_detect_title_author_merges_multiline_title(pdf_with_multiline_cover_title_bytes):
    """Regresyon: aynı (en büyük) puntoda birden çok satıra yayılmış bir
    başlığın eskiden yalnızca ilk satırı alınıyordu."""
    doc = pymupdf.open(stream=pdf_with_multiline_cover_title_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Buyuk Baslik Ikinci Satiri"
    assert author == "Yazar Adi"


def test_detect_title_author_ocrs_scanned_cover(scanned_cover_pdf_bytes):
    """Kapakta metin katmanı yoksa (taranmış/görsel kapak), artık OCR ile
    aynı büyük-satır/küçük-satır heuristiği satır yüksekliği üzerinden
    denenmeli — eskiden bu durumda doğrudan (None, None) dönüyordu."""
    doc = pymupdf.open(stream=scanned_cover_pdf_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title is not None and "COVER" in title.upper()
    assert author is not None and "AUTHOR" in author.upper()


def test_analyze_pdf_reports_warnings_for_missing_fields(blank_pdf_bytes):
    result = analyze_pdf(blank_pdf_bytes)
    assert result["title"] is None
    assert result["author"] is None
    assert result["chapters"] == []
    assert set(result["warnings"]) == {"title", "author", "chapters"}


def test_analyze_pdf_omits_warnings_for_detected_fields(pdf_with_metadata_bytes):
    result = analyze_pdf(pdf_with_metadata_bytes)
    assert result["title"] == "Metadata Basligi"
    assert result["author"] == "Metadata Yazari"
    assert "title" not in result["warnings"]
    assert "author" not in result["warnings"]
    assert "chapters" in result["warnings"]  # bu PDF'te TOC yok


def test_analyze_pdf_raises_on_invalid_pdf(corrupt_pdf_bytes):
    with pytest.raises(ConversionError):
        analyze_pdf(corrupt_pdf_bytes)


def test_extract_page_text_preserves_paragraph_breaks(pdf_with_two_paragraphs_bytes):
    doc = pymupdf.open(stream=pdf_with_two_paragraphs_bytes, filetype="pdf")
    text = extract_page_text(doc[0])
    doc.close()

    assert text is not None
    assert "birinci paragraftir" in text
    assert "ikinci paragraftir" in text
    # iki blok da metinde var, aralarında paragraf ayracı (bos satir) olmali
    assert "\n\n" in text


def test_fix_mac_turkish_mojibake_corrects_known_substitutions():
    from converter import _fix_mac_turkish_mojibake

    garbled = "B‹L‹MSEL B‹R MAKALE, AﬁKAR, e¤itim, ba¤lant›"
    fixed = _fix_mac_turkish_mojibake(garbled, has_macroman_font=True)

    assert fixed == "BİLİMSEL BİR MAKALE, AŞKAR, eğitim, bağlantı"


def test_fix_mac_turkish_mojibake_noop_without_macroman_font():
    from converter import _fix_mac_turkish_mojibake

    garbled = "B‹L‹MSEL"
    assert _fix_mac_turkish_mojibake(garbled, has_macroman_font=False) == garbled


def test_fix_mac_turkish_mojibake_noop_without_tell_characters():
    from converter import _fix_mac_turkish_mojibake

    # '¤' tek başına (ör. gerçek bir para birimi işareti) yanlış tetiklememeli --
    # yalnızca güçlü işaretçiler (‹ › ﬁ ﬂ) varken düzeltme uygulanır.
    text_with_currency_sign = "Fiyat: ¤100"
    assert _fix_mac_turkish_mojibake(text_with_currency_sign, has_macroman_font=True) == text_with_currency_sign


def test_extract_page_text_reorders_two_column_layout(pdf_with_two_columns_bytes):
    """İki sütunlu bir sayfada okuma sırası önce tüm sol sütun, sonra tüm
    sağ sütun olmalı -- `get_text('blocks', sort=True)`'in varsayılan
    y-sonra-x sıralaması bunu satır satır (row-major) karıştırırdı.

    Regresyon testi: fixture bloklarını kasıtlı olarak önce SAĞ sonra SOL
    sütun sırasıyla ekliyor, PDF'in ham obje sırasının etkisiz olduğunu
    doğrulamak için."""
    doc = pymupdf.open(stream=pdf_with_two_columns_bytes, filetype="pdf")
    text = extract_page_text(doc[0])
    doc.close()

    assert text is not None
    for line in [
        "Sol sutun ilk paragraf",
        "Sol sutun ikinci paragraf",
        "Sol sutun ucuncu paragraf",
        "Sag sutun ilk paragraf",
        "Sag sutun ikinci paragraf",
        "Sag sutun ucuncu paragraf",
    ]:
        assert line in text, f"'{line}' metinde bulunamadı"

    # sol sütunun SON satırı bile sağ sütunun İLK satırından önce gelmeli
    left_last_idx = text.index("Sol sutun ucuncu paragraf")
    right_first_idx = text.index("Sag sutun ilk paragraf")
    assert left_last_idx < right_first_idx, "sol sütun tamamen sağ sütundan önce gelmeli"


def test_convert_pdf_to_epub_keeps_paragraphs_as_separate_p_tags(pdf_with_two_paragraphs_bytes):
    config = {"title": "Paragraf Testi"}
    result = convert_pdf_to_epub(pdf_with_two_paragraphs_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        chapter_files = [name for name in archive.namelist() if name.endswith(".xhtml") and "chap" in name]
        content = archive.read(chapter_files[0]).decode("utf-8")

    # Regresyon testi: eskiden get_text("text") tum sayfayi tek bir <p>'ye
    # duzlestiriyordu (paragraf araligi/bicimlendirme kayboluyordu).
    assert content.count("<p>") >= 2
    assert "birinci paragraftir" in content
    assert "ikinci paragraftir" in content


# --- Plan/map/reduce'a özgü yeni testler ------------------------------------

def test_plan_conversion_splits_into_chunk_page_size_chunks(multi_chunk_pdf_bytes):
    """30 sayfalık bir PDF, CHUNK_PAGE_SIZE (25) sayfalık chunk'lara bölünmeli."""
    plan = plan_conversion(multi_chunk_pdf_bytes, {"title": "Cok Sayfali"})

    assert plan.total_pages == 30
    assert plan.chunks == [(1, CHUNK_PAGE_SIZE), (CHUNK_PAGE_SIZE + 1, 30)]


def test_convert_pdf_to_epub_reassembles_chapter_spanning_multiple_chunks(multi_chunk_pdf_bytes):
    """Bir bölüm birden fazla chunk'a yayılsa bile (chunk sınırından bağımsız),
    sayfa numarası sırasına göre doğru şekilde birleştirilmeli."""
    config = {
        "title": "Cok Sayfali",
        "chapters": [{"start_page": 1, "title": "Tek Bolum"}],
    }
    result = convert_pdf_to_epub(multi_chunk_pdf_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        content = archive.read("EPUB/chap_01.xhtml").decode("utf-8")

    assert "sayfa 1 " in content.lower()
    assert "sayfa 30 " in content.lower()


# --- Kenar payı kalibrasyonuna özgü testler ---------------------------------

def test_detect_header_footer_margins_skips_calibration_for_short_books(sample_pdf_bytes):
    """20 sayfa altındaki kitaplarda örneklem güvenilmez olduğundan kalibrasyon
    atlanmalı, sabit varsayılan orana düşülmeli."""
    plan = plan_conversion(sample_pdf_bytes, {"title": "Kisa Kitap"})
    assert plan.resolved_config["header_margin_ratio"] == HEADER_FOOTER_DEFAULT_MARGIN_RATIO
    assert plan.resolved_config["footer_margin_ratio"] == HEADER_FOOTER_DEFAULT_MARGIN_RATIO


def test_detect_header_footer_margins_catches_pattern_outside_default_band(
    pdf_with_recurring_header_footer_bytes,
):
    """Sabit %8 varsayılan kenar payının kaçıracağı (~%11'de duran) ama kitap
    boyunca tekrar eden bir koşu başlığı/sayfa no örüntüsü, dinamik
    kalibrasyonla tespit edilip her sayfada kırpılmalı."""
    plan = plan_conversion(pdf_with_recurring_header_footer_bytes, {"title": "Kalibrasyon Testi"})

    assert plan.resolved_config["header_margin_ratio"] > HEADER_FOOTER_DEFAULT_MARGIN_RATIO
    assert plan.resolved_config["footer_margin_ratio"] > HEADER_FOOTER_DEFAULT_MARGIN_RATIO

    page_results = process_page_range(pdf_with_recurring_header_footer_bytes, 1, 22, plan.resolved_config)
    combined = "\n".join(pr.html for pr in page_results)

    assert "kosu basligi" not in combined.lower()
    assert "gercek bir paragraftir" in combined.lower()
    # Header/footer tamamen kırpılmışsa her sayfadan tam olarak bir <p> kalmalı.
    assert combined.count("<p>") == 22
