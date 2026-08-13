# Publisco Conversion Evaluation Framework

PDF → EPUB dönüştürme kalitesini objektif olarak ölçmek, ve her conversion/OCR/LLM
değişikliğinin gerçekten iyileştirme mi getirdiğini (yoksa regresyon mu) göstermek
için. Pipeline koduna (`converter.py` / `main.py`) hiç dokunmaz -- yalnızca onu
lokalde (Modal'sız) çalıştırıp çıktısını ölçer.

## Hızlı başlangıç

```bash
cd modal_worker
.venv/bin/pip install -r eval/requirements-eval.txt   # ilk kurulum
pnpm test:conversion --smoke                            # kök dizinden, sentetik kitaplarla
# veya doğrudan:
.venv/bin/python -m eval.run --smoke
```

Golden dataset'te gerçek kitap yoksa (yeni checkout) `--smoke` sentetik, kod
içinde üretilen 3 kitapla mekaniği doğrular -- her zaman çalışır.

### Opsiyonel araçlar

- `brew install epubcheck` -- EPUB validity metriği ve gate'i için gerekir,
  kurulu değilse metrik sessizce devre dışı kalır (skoru etkilemez, terminalde
  uyarı basılır).
- `.venv/bin/pip install wordfreq` -- broken-words metriği için (`requirements-eval.txt`'te zaten var).
- Yerel `tesseract`'ın golden dataset'teki dillerin hepsi için dil paketi kurulu
  olmalı (`brew install tesseract-lang`) -- yoksa OCR metriği o dillerde çalışmaz.

## Komutlar

```bash
pnpm test:conversion                        # tüm golden set, baseline ile karşılaştır
pnpm test:conversion --smoke                # yalnız sentetik smoke kitaplar
pnpm test:conversion --book book-007        # tek kitap + tam diagnostic
pnpm test:conversion --save-baseline        # bu koşuyu yeni baseline yap
pnpm test:conversion --variant llm-v1       # sonucu bir etiketle kaydet (LLM karşılaştırması için)
pnpm test:conversion --compare a.json b.json  # iki kayıtlı sonucu karşılaştır
```

Sonuçlar `eval/results/<timestamp>-<variant>.json`'a kaydedilir (gitignored).
Baseline `eval/baselines/baseline.json`'da tutulur (**commit edilir** -- bu
regresyon referansımız).

## Mimari

```
eval/
├── runner.py          PDF -> plan/map/reduce'u lokalde çalıştırır (converter.py'yi çağırır, değiştirmez)
├── epub_reader.py      Üretilen EPUB'ı paragraf/başlık/TOC/görsel listesine çözer
├── evaluate.py          Bir kitap için: dönüştür -> oku -> tüm metrikleri hesapla -> skorla
├── scoring.py            Ham metriklerden 0-100 skor (ağırlıklı + hard gate'ler)
├── report.py              Terminal özeti + JSON kayıt + baseline karşılaştırma
├── run.py                  CLI giriş noktası
├── metrics/                 Her biri bağımsız, tek bir şeyi ölçen modül
└── golden/
    ├── types.py             GoldenBook veri yapısı
    ├── synthetic.py         Kod içinde üretilen smoke kitaplar (--smoke)
    ├── loader.py             manifest.json + books/ 'dan gerçek kitapları yükler
    ├── add_book.py           Yeni kitap ekleme yardımcı CLI'ı
    ├── manifest.json         Gerçek kitapların listesi (commit edilir)
    └── books/<id>/           input.pdf (gitignored) + metadata.json + opsiyonel reference.txt
```

## Referans veri stratejisi (hybrid, iki katmanlı)

Her kitapta tam bir "doğru" EPUB/metin elle üretmiyoruz -- haftalarca sürer.
Bunun yerine:

1. **Referanssız metrikler** (her kitapta, sıfır manuel emek): duplicate
   text, broken words, OCR confidence, EPUB validity, PDF-içi görsel sayısı
   vs EPUB görsel sayısı.
2. **Tier-1 referans** (`metadata.json`, ~10-15 dk/kitap): `must_include_phrases`
   / `must_exclude_phrases` (birkaç ayırt edici cümle -- tam metin yazmadan
   recall + header-sızıntısı kontrolü), `expected_chapters`, `expected_image_count`,
   `expected_paragraph_range`.
3. **Tier-2 referans** (`reference.txt`, yalnız birkaç kitap): bağımsız
   kaynaklı tam referans metin (Project Gutenberg / Wikisource gibi
   public-domain kaynaklardan bedavaya gelir, elle yazılmaz). Word
   recall/precision ve 5-gram reading-order metriklerini tam güçle çalıştırır
   -- LLM eklendiğinde "model uydurdu mu?" sorusunu burada cevaplarız
   (word precision düşerse model referansta olmayan kelime üretiyor demektir).

## Kitap ekleme

```bash
.venv/bin/python -m eval.golden.add_book ~/Downloads/kitap.pdf book-001-ornek normal-text-novel
```

Bu, `books/book-001-ornek/input.pdf`'i kopyalar, `manifest.json`'a sha256 ile
bir girdi ekler, ve doldurulacak bir `metadata.json` iskeleti oluşturur.
`metadata.json`'daki `TODO` alanlarını doldur (`language`, `must_include_phrases`
vb.). Tam referans metin eklemek istiyorsan (Tier-2) aynı dizine `reference.txt`
koy.

### 15 kategori + kaynak önerileri

| Kategori | Örnek kaynak |
|---|---|
| `normal-text-novel` | Project Gutenberg (EPUB'dan PDF'e dönüştürülmüş herhangi bir roman) |
| `scanned-novel` | Internet Archive (`archive.org`) taranmış roman |
| `poor-quality-scan` | Internet Archive, düşük çözünürlüklü/eski tarama |
| `bad-ocr-layer` | Zaten kötü OCR metin katmanı olan bir PDF (Google Books vb.) |
| `two-column-academic` | arXiv makalesi |
| `book-with-images` | Görsel ağırlıklı bir kitap/rehber |
| `book-with-tables` | Tablo içeren teknik/akademik bir doküman |
| `book-with-footnotes` | Dipnotlu akademik bir kitap |
| `technical-with-code` | Açık kaynak bir programlama kitabı (ör. `progit`) |
| `turkish` | Türkçe bir e-kitap |
| `english` | İngilizce bir e-kitap |
| `multilingual` | Birden fazla dil içeren bir doküman |
| `complex-headings` | Çok seviyeli başlık hiyerarşisi olan bir kitap |
| `lists-and-quotes` | Liste/alıntı ağırlıklı bir kitap |
| `unusual-fonts` | Özel/subset font kullanan bir PDF |
| `mathematical` (unsupported) | `metadata.json`'da `"unsupported": true` -- skora dahil edilmez, yalnızca raporlanır |

Tüm kaynaklar telifsiz/public-domain olmalı (repository'ye PDF girmiyor ama
yine de yasal netlik için).

## Skorlama modeli

```
Text completeness (recall %60 + precision %40)   35
Structure (paragraf %10 + heading/TOC %10)        20
Text cleanliness (duplicate %8 + broken words %7) 15
OCR quality                                       10
Images                                            10
Reading order (5-gram overlap)                    10
```

Bir bileşen ölçülemiyorsa (ör. referanssız kitapta reading-order) dışlanır,
kalan ağırlıklar yeniden normalize edilir. Hard gate'ler: epubcheck error/fatal
varsa skor ≤59 (Poor); metin tamlığı <%50 ise skor ≤39 (Failed).

Kategoriler: 90-100 Excellent · 75-89 Good · 60-74 Fair · 40-59 Poor · 0-39 Failed.

## LLM / variant karşılaştırması

`--variant` etiketiyle kaydedilen sonuçlar aynı JSON şemasını paylaşır --
`--compare baseline.json llm-v1.json` ile "LLM gerçekten değer katıyor mu"
sorusu doğrudan cevaplanır (ör. deterministic 78 → LLM 79 ise maliyete değmez).

## Testler

```bash
.venv/bin/python -m pytest tests/test_eval_metrics.py
```
