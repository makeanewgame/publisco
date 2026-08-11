# PDF'den Kindle uyumlu EPUB yapma

Bu proje taranmış veya metin tabanlı PDF'yi **reflowable EPUB 3** dosyasına dönüştürür. Üretilen kitapta Kindle üzerinden yazı tipi, punto, satır aralığı ve kenar boşlukları değiştirilebilir.

> Önemli: Taranmış PDF'lerde sonuç OCR kalitesine bağlıdır. Çok sütunlu, eğri, gölgeli veya düşük çözünürlüklü sayfalarda elle düzeltme gerekebilir.

## 1. VS Code hazırlığı

1. Bilgisayarına Python 3.11 veya 3.12 kur.
2. VS Code'a Microsoft'un **Python** eklentisini kur.
3. Bu klasörü VS Code ile aç.
4. VS Code'da `Terminal > New Terminal` seç.

## 2. Sistem programlarını kur

### macOS

Önce Homebrew yoksa [brew.sh](https://brew.sh/) üzerinden kur. Ardından:

```bash
brew install tesseract tesseract-lang poppler ghostscript qpdf
```

### Windows

En sorunsuz yöntem Chocolatey kullanmaktır. PowerShell'i yönetici olarak aç:

```powershell
choco install python tesseract poppler ghostscript qpdf -y
```

Tesseract kurulumunda Türkçe dil verisinin bulunduğunu kontrol et:

```powershell
tesseract --list-langs
```

Listede `tur` görünmelidir. Görünmüyorsa `tur.traineddata` dosyasını Tesseract'ın `tessdata` klasörüne ekle.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install python3-venv tesseract-ocr tesseract-ocr-tur poppler-utils ghostscript qpdf
```

## 3. Python ortamını kur

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

VS Code interpreter sorarsa `.venv` içindeki Python'u seç.

## 4. PDF'yi dönüştür

PDF dosyanı proje klasörüne koy. Örnek:

```bash
python pdf_to_kindle_epub.py kitap.pdf --title "Kitap Adı" --author "Yazar Adı"
```

Çıktı adını ayrıca belirlemek için:

```bash
python pdf_to_kindle_epub.py kitap.pdf -o kitap-kindle.epub --title "Kitap Adı" --author "Yazar Adı"
```

Taranmış PDF algılanırsa Türkçe OCR otomatik uygulanır. 300 sayfalık bir kitap bilgisayara göre birkaç dakika veya daha uzun sürebilir.

## 5. Bölümler yanlış algılanırsa

PDF'deki gerçek bölüm başlangıç sayfalarını virgülle ver:

```bash
python pdf_to_kindle_epub.py kitap.pdf -o kitap.epub --title "Kitap Adı" --author "Yazar" --chapter-pages "6,10,14,19,24"
```

Kitap adı/yazar adı her sayfada üstbilgi olarak tekrarlanıyorsa silebilirsin:

```bash
python pdf_to_kindle_epub.py kitap.pdf -o kitap.epub --header "YAZAR ADI" --header "KİTAP ADI"
```

`--header` değeri bir düzenli ifadedir. Tam satır eşleşmelerini siler.

## 6. Kindle'a gönder

1. [Send to Kindle](https://www.amazon.com/sendtokindle) sayfasını aç.
2. EPUB dosyasını yükle.
3. Kindle cihazını veya uygulamasını eşitle.

USB ile doğrudan kopyalamak yerine Send to Kindle kullanmak EPUB dönüşümünü daha güvenilir yapar.

## Sık karşılaşılan hatalar

### `Eksik programlar` hatası

Sistem paketlerinden biri kurulmamış veya PATH'e eklenmemiştir. Terminalde şunları dene:

```bash
tesseract --version
tesseract --list-langs
pdfinfo -v
ocrmypdf --version
```

### Türkçe harfler yanlış çıkıyor

`tesseract --list-langs` çıktısında `tur` olduğundan emin ol. Ardından komutu varsayılan `--language tur` ile çalıştır.

### Yazı boyutu Kindle'da değişmiyor

Bu genellikle PDF'nin sayfa görüntülerinin EPUB içine resim olarak konmasıyla olur. Bu proje ana metni OCR ile gerçek metne dönüştürdüğü için font/punto ayarı çalışır.

### Metin sırası karışıyor

Kaynak sayfa iki sütunluysa veya aynı PDF sayfasında iki kitap sayfası varsa OCR okuma sırası bozulabilir. Böyle dosyalarda önce sayfaları bölmek veya OCR metnini elle düzeltmek gerekir.
