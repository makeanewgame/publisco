# publisco Worker (FastAPI)

PDF → EPUB dönüştürme servisi. `apps/api` (NestJS), dosyayı S3'e koymadan önce
dönüştürme işini bu servise devreder: PDF'i yükler, EPUB baytlarını geri alır.

`pdf_to_epub_kit/pdf_to_epub.py` betiğiyle karıştırmayın — o, kendi
`pdf_to_epub_kit/README.md`'sinde tarif edildiği gibi tek başına
kopyalanabilen bağımsız bir CLI kiti. Bu servis aynı dönüştürme mantığının
`app/converter.py` içinde yaşayan, tamamen bellek üzerinde çalışan (disk
kullanmayan) API sürümüdür.

## Kurulum

`requirements.txt`'teki `fastapi==0.141.1` Python 3.10+ ister. Sisteminizdeki
`python3 --version` 3.10'un altındaysa (örn. macOS'un ön yüklü 3.9.6'sı),
önce izole bir sürüm kurun — bu, global `python3`'e dokunmaz:

```bash
brew install python@3.12   # sadece bir kere, sistem python3'ünü değiştirmez
```

```bash
cd apps/worker
python3.12 -m venv .venv   # python3 3.10+ ise doğrudan "python3 -m venv .venv" da olur
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # sadece çalıştırmak için: requirements.txt yeterli
```

## Çalıştırma

```bash
uvicorn app.main:app --reload --port 8000
```

- `GET /health` — sağlık kontrolü
- `POST /convert` — multipart form:
  - `file` (zorunlu): `.pdf` dosyası
  - `title`, `author`, `language` (opsiyonel)
  - `options` (opsiyonel): `book_config.json` ile aynı şemada JSON string
    (`chapters`, `diagram_pages`, `visual_mode`, `max_epub_size_mb`, vb. — bkz.
    kök dizindeki `book_config.example.json`)
  - `force_ocr` (opsiyonel, bool)

  Yanıt, `application/epub+zip` içerikli EPUB dosyasının kendisidir
  (`Content-Disposition: attachment`).

## Test

```bash
pytest
```

## OCR (opsiyonel)

`pytesseract` `requirements.txt`'te (kod tarafı her zaman hazır); taranmış/
görüntü PDF sayfaları için OCR'ın gerçekten çalışması için sisteme ayrıca
Tesseract OCR binary + ilgili dil paketleri kurulmalı (bkz. "Sunucu
Paketleri" bölümü). Kurulu değilse servis sessizce OCR'siz devam eder.

## Sunucu Paketleri (Deployment)

Bu bölüm, kod `pip install -r requirements.txt` ile kurulmayan (yani
Python paket yöneticisinin dışında, işletim sistemine kurulması gereken)
tüm bağımlılıkları listeler. **Yeni bir sistem paketi/dil desteği
eklendiğinde bu bölüm de güncellenmelidir.**

### Zorunlu

- Python 3.10+ (bkz. yukarıdaki "Kurulum")

### OCR / çoklu dil tespiti için (opsiyonel ama önerilir)

- `pytesseract` Python paketi — `requirements.txt`'e dahil (kod tarafı
  hazır); asıl sistem bağımlılığı aşağıdaki Tesseract binary + dil
  paketleridir, onlar kurulu değilse OCR'siz sessizce devam eder.
- Tesseract OCR binary
- Aşağıdaki Tesseract dil paketleri, `app/converter.py` içindeki
  `LANGUAGE_MAP`'te tanımlı her dil için (bu tablo `LANGUAGE_MAP` ile
  senkron tutulmalı):

  | Dil | ISO kodu (`language`) | Tesseract kodu (`ocr_language`) | apt paketi |
  |-----|------------------------|----------------------------------|------------|
  | Türkçe | `tr` | `tur` | `tesseract-ocr-tur` |
  | İngilizce | `en` | `eng` | `tesseract-ocr-eng` |
  | Almanca | `de` | `deu` | `tesseract-ocr-deu` |
  | Fransızca | `fr` | `fra` | `tesseract-ocr-fra` |
  | İspanyolca | `es` | `spa` | `tesseract-ocr-spa` |
  | İtalyanca | `it` | `ita` | `tesseract-ocr-ita` |
  | Portekizce | `pt` | `por` | `tesseract-ocr-por` |
  | Felemenkçe | `nl` | `nld` | `tesseract-ocr-nld` |
  | Rusça | `ru` | `rus` | `tesseract-ocr-rus` |
  | Arapça | `ar` | `ara` | `tesseract-ocr-ara` |
  | Lehçe | `pl` | `pol` | `tesseract-ocr-pol` |
  | İsveççe | `sv` | `swe` | `tesseract-ocr-swe` |
  | Yunanca | `el` | `ell` | `tesseract-ocr-ell` |
  | Japonca | `ja` | `jpn` | `tesseract-ocr-jpn` |
  | Korece | `ko` | `kor` | `tesseract-ocr-kor` |
  | Çince (Basit) | `zh-cn` | `chi_sim` | `tesseract-ocr-chi-sim` |
  | Çince (Geleneksel) | `zh-tw` | `chi_tra` | `tesseract-ocr-chi-tra` |

  Ubuntu/Debian:

  ```bash
  sudo apt-get update
  sudo apt-get install -y tesseract-ocr \
    tesseract-ocr-tur tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra \
    tesseract-ocr-spa tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-nld \
    tesseract-ocr-rus tesseract-ocr-ara tesseract-ocr-pol tesseract-ocr-swe \
    tesseract-ocr-ell tesseract-ocr-jpn tesseract-ocr-kor \
    tesseract-ocr-chi-sim tesseract-ocr-chi-tra
  ```

  macOS (Homebrew):

  ```bash
  brew install tesseract tesseract-lang   # tesseract-lang tüm dil paketlerini kurar
  ```

  `pytesseract` ayrıca kurulmaz — `requirements.txt`'te olduğu için venv
  kurulumunda (`pip install -r requirements.txt`) zaten geliyor.

  Not: Tesseract binary/dil paketleri kurulu olmasa da servis çökmez —
  sadece taranmış (görüntü) sayfalarda metin çıkaramaz ve otomatik dil
  tespiti yalnızca gömülü metni olan sayfalarla sınırlı kalır (bkz. altta
  "Çoklu dil / otomatik dil tespiti").

## Çoklu dil / otomatik dil tespiti

`language` ve `options.ocr_language` alanlarına `"auto"` gönderilirse belge
dili otomatik tespit edilir: önce gömülü metinden (varsa), yoksa ilk sayfanın
geniş bir dil setiyle (`tur+eng`) OCR'ından örnek metin alınıp `langdetect`
ile dil tahmin edilir; tahmin edilen ISO koduna karşılık gelen Tesseract dil
kodu (bkz. `converter.py` içindeki `LANGUAGE_MAP`) OCR için kullanılır, ISO
kodu ise EPUB'un `dc:language` alanına yazılır. Belirli bir dil biliniyorsa
`language`'a ISO 639-1 kodu (`tr`, `en`, `de`, ...), `options.ocr_language`'a
ise doğrudan Tesseract dil kodu (`tur`, `eng`, `deu`, ...) gönderilebilir;
birden fazla dil karışık geçiyorsa `"tur+eng"` gibi `+` ile birleştirilebilir.
Otomatik tespit için `langdetect` paketi (`requirements.txt`'te mevcut) ve
tespit edilecek dile karşılık gelen Tesseract dil paketinin kurulu olması
gerekir.
