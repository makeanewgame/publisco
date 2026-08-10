# PDF → Kindle EPUB Kiti — VS Code + Codex Rehberi

## Bu kitte ne var?

```
pdf_to_epub_kit/
├── pdf_to_epub.py            # Ana dönüştürme betiği (çalışır durumda)
├── book_config.example.json  # Ayar dosyası şablonu
├── requirements.txt          # Gerekli Python paketleri
├── tests/                    # Betiğin birim testleri
└── README.md                 # Bu dosya
```

Betik Gemini'nin sade yaklaşımı (saf Python, ağır kurulum yok) ile
ChatGPT'nin eksik olan özelliklerini (bölüm ayırma, kapak, şema/tablo
sayfalarını görsel olarak koruma) birleştiriyor. OCR isteğe bağlı ve
kurulu değilse betik çökmeden devam ediyor.

---

## 1. Senin yapman gerekenler (Codex'e bırakma)

Bunlar ortam kurulumu — bir ajanın yapması senden daha yavaş/riskli
olur, elle yapman daha sağlıklı:

1. **Python 3.10+ kurulu olduğunu doğrula**
   Terminalde: `python3 --version` (Windows'ta `py --version`)
   Yoksa [python.org](https://python.org)'dan indir.

2. **Bu üç dosyayı indir** (aşağıda paylaşacağım) ve bir klasöre koy,
   örneğin `pdf_to_epub_kit/`. PDF kitabını da aynı klasöre kopyala.

3. **VS Code'da klasörü aç**: `File > Open Folder` → `pdf_to_epub_kit`.

4. **Sanal ortam kur ve paketleri yükle** (VS Code terminalinde):
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **`book_config.example.json`'ı kopyalayıp `book_config.json` yap**,
   kendi kitabına göre doldur:
   - `title`, `author`
   - `start_page` / `end_page`: PDF görüntüleyicide gördüğün gerçek
     PDF sayfa numaraları (kitaptaki basılı numaralarla karışmasın)
   - `chapters`: her bölümün başladığı sayfa + başlık
   - `cover_page`: kapak yapılacak sayfa
   - `diagram_pages`: görsel olarak da korunması gereken tablo/şema
     sayfaları (varsa)

   Bu bilgileri (kaç bölüm var, hangi sayfada başlıyor) sadece sen
   bilebilirsin — PDF'i açıp bakman gerekiyor, bunu otomatikleştirmek
   güvenilir değil.

6. **İlk denemeyi elle çalıştır**, betiğin gerçekten çalıştığını gör:
   ```bash
   python3 pdf_to_epub.py kitap.pdf -c book_config.json
   ```

7. **Çıktıyı kontrol et**: EPUB'u Calibre veya Apple Books ile aç,
   bölümler ve Türkçe karakterler (ç, ğ, ı, ş, ü, ö) doğru mu bak.

8. **Kindle'a gönder**: Amazon hesabındaki *Send to Kindle* sayfasından
   EPUB'u yükle. USB ile kopyalamayı deneme, çoğu Kindle modeli EPUB'u
   doğrudan açmıyor.

---

## 2. Codex'e bırakabileceğin kısımlar

Elindeki `pdf_to_epub.py`'yi Codex'e **başlangıç noktası** olarak ver,
sıfırdan yazdırma — üstüne şu tür geliştirmeleri yaptırmak verimli olur:

- Betikte hata çıkarsa (paket sürüm uyuşmazlığı, JSON hatası vb.)
  debug ettirmek
- `--force-ocr` gibi seçenekleri genişletmek
- İki sütunlu PDF'lerde metin sırası karışıyorsa okuma mantığını
  iyileştirmek
- Bölüm başlıklarını PDF içinden otomatik tespit etmeye çalışan bir
  ek mod yazdırmak (elle `chapters` girmek yerine)
- Çıktı EPUB'un CSS/stilini (yazı tipi, boşluklar) özelleştirmek
- `.vscode/tasks.json` gibi bir VS Code görevi oluşturup komutu
  tek tıkla çalıştırılır hale getirmek

Kısacası: **ortamı sen kur, ilk çalıştırmayı sen doğrula; kod
üzerindeki iyileştirme/hata ayıklama döngüsünü Codex'e devret.**

---

## Sık karşılaşılabilecek sorunlar

| Sorun | Çözüm |
|---|---|
| `ModuleNotFoundError: fitz` | `pip install pymupdf` (paket adı farklı, import adı `fitz`) |
| Bölümler içindekilerde yok | `book_config.json`'daki `chapters` listesini kontrol et, JSON virgülleri doğru mu bak |
| Bazı sayfalar atlandı uyarısı | O sayfalar taranmış/görüntü olabilir; OCR için `pip install pytesseract pillow` + sisteme Tesseract kurmak gerekir |
| Türkçe karakterler bozuk | `language` alanının `"tr"` olduğundan emin ol |


hadi kolay gelsin
