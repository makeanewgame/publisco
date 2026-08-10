# Notlar ve Yapılacaklar

Bu dosya, proje hakkında düşüncelerini, fikirlerini ve karşılaştığın sorunları kaydetmen için hazırlanmıştır.

Tamamlanan maddeler burada kalabalık yapmasın diye [`TAMAMLANANLAR.md`](./TAMAMLANANLAR.md) dosyasına taşınıyor. Bir madde tamamlanırken ileride yapılması gereken bir iş ortaya çıkarsa, o iş ayrı bir madde olarak burada kalır.

## Yapılacaklar
- [ ] SQL injection testleri yapılsın (bitince)
- [ ] Şifremi unuttum akışında artık hesabın kayıtlı olup olmadığı sızdırılıyor (enumeration riski) — `AuthService.forgotPassword`'ün kayıtsız e-posta için 404 dönmesi bilinçli bir tercih olarak eklendi, ama halka açık/production bir ortama çıkmadan önce bu davranış tekrar değerlendirilmeli (rate limiting, captcha vb. önlemler düşünülebilir)
- [ ] Kota limitleri artık kullanıcı bazlı ayrı bir tabloda (`UserQuota`, `apps/api/prisma/schema.prisma`) tutuluyor ama bunu değiştirecek bir admin endpoint/UI yok — şu an sadece signup'ta tier'ın varsayılan değerleriyle dolduruluyor, kimseye özel limit tanımlanamıyor
- [ ] `apps/worker` bu deploy kapsamında değildi, Vercel'e (veya başka bir yere) deploy edilmedi — production'daki `WORKER_URL` (api tarafı) ve `VITE_WORKER_URL` (web tarafı) hâlâ `localhost`'a işaret ediyor, yani prod'da `/convert` ve `/analyze` (kapak/başlık tespiti) çalışmaz. Worker bir yere deploy edildiğinde her iki env değişkeni de gerçek worker URL'iyle güncellenmeli (`vercel env add WORKER_URL production/preview` → `apps/api`, `vercel env add VITE_WORKER_URL production/preview` → `apps/web`)

## Fikirler
- [ ] Responsive tasarım olsun -- v1
- [ ] 50 MB'dan büyük dosyaları Kindle kabul etmiyor — bu limit arayüzde kontrol edilmeli -- lately v1
- [ ] eğlenceli temaya karar verince sitede 2 tema olsun biri eğlenceli diğeri ciddi switchin bir ucu fun diğer ucu ciddi olsun -- v2
- [ ] Kullanıcı font seçimi yapabilsin -- v2
- [ ] maille Kindle'a gönderebilsin -- v2
- [ ] Uygulama dil desteklerine ispanyolca da eklensin -- v2
- [ ] convert edilecek dokümanlara ön izleme özelliği ekleyelim -- v2

## Sorunlar (Buglar)
- [x] Vercel'de web deploy'u, `apps/api`'nin `postinstall` (`prisma generate`) script'i `PRISMA_DATABASE_URL` bulamadığı için install adımında patlıyordu — monorepo kökünde `pnpm install` çalıştığı için tüm workspace paketlerinin postinstall'ı tetikleniyor. `pnpm install --filter=<pkg>...` bunu ÇÖZMÜYOR: yerelde doğrulandı, filtreli install'da bile `apps/api`'nin kendi lifecycle script'i (ve tüm bağımlılıkları) yine kuruluyor — pnpm bu install modunda sibling workspace paketlerinin script'lerini atlamıyor. Asıl çözüm: `apps/api/package.json`'daki `postinstall`, `PRISMA_DATABASE_URL` set değilse `prisma generate`'i sessizce atlayacak şekilde korumaya alındı (`[ -z "$PRISMA_DATABASE_URL" ] && echo ... || prisma generate`). Vercel'deki custom Install Command (`--filter=web...`) artık gereksiz, gerekirse default'a geri alınabilir.
- [ ] `FloatingThemeToggle.tsx` hem `RootLayout.tsx`'te hem `Navbar.tsx`'te import ediliyor ama hiçbir yerde `<FloatingThemeToggle />` olarak render edilmiyor (ölü kod) — component'in kendi konumlama class'ı da eksik (`right-4 top-4` var ama `fixed`/`absolute` yok, render edilse bile ekranda konumlanmazdı). Kullanılacaksa gerçekten JSX'e eklenip pozisyon class'ı düzeltilmeli, kullanılmayacaksa silinmeli.

## Çözüm Önerileri
- [ ] Convert'teki İptal butonu artık istemciyi sonucu beklemekten vazgeçiriyor ama worker'daki arka plan job'unu (`apps/worker/app/jobs.py`, `ThreadPoolExecutor`) sunucu tarafında durdurmuyor — job kullanıcı vazgeçtikten sonra da OCR/CPU kaynağını tüketmeye devam ediyor. Gerçek bir sunucu-taraflı iptal için worker'a bir cancel endpoint'i (job'ı "cancelled" işaretleyip sayfa döngüsünün bir sonraki adımda kontrol edip erken çıkması) ve api'nin bunu proxy'lemesi gerekiyor.
