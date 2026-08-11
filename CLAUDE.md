# publisco - Turbo Monorepo Project Guide

## 🏗️ Project Structure

```
publisco/
├── apps/
│   ├── web/          # React + Vite frontend (port 3000)
│   └── api/          # NestJS backend (port 3001)
├── modal_worker/      # Modal (Python) PDF -> EPUB pipeline — NOT a pnpm/turbo workspace member
├── pnpm-workspace.yaml
├── turbo.json
└── package.json
```

PDF→EPUB dönüştürme artık Hostinger'daki bir FastAPI worker'da değil, **Modal.com**'da (`modal_worker/`) dağıtık (map-reduce, sayfa aralıklarına göre paralel container) çalışıyor. `modal_worker/` bir pnpm/turbo workspace üyesi değil (Python-only) — `pnpm dev` bu yüzden yalnızca web + api'yi başlatır, Modal ayrı deploy edilir (bkz. aşağıdaki "Modal Worker" bölümü).

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- pnpm (package manager)
- Python 3.12+ ve [Modal CLI](https://modal.com/docs/guide) (`pip install modal && modal setup`) — yalnızca `modal_worker/`'ı deploy edecek/lokal test edecekseniz gerekir, `pnpm dev` için gerekmez

### Running the Project

**Option 1: Web + API birlikte**
```bash
pnpm dev
```
- Frontend: http://localhost:3000
- Backend API: http://localhost:3001

**Option 2: Individual services**
```bash
# Frontend only
pnpm --filter web dev

# Backend only
pnpm --filter api start:dev
```

**Modal worker (ayrı, pnpm dışı):**
```bash
cd modal_worker
modal serve main.py   # lokal geliştirme — sıcak-reload'lu geçici bir endpoint verir
modal deploy main.py  # prod deploy — apps/api/.env'deki MODAL_ENDPOINT_URL bu deploy'un base URL'ini işaret etmeli
```

## 🔧 Tech Stack

### Frontend (apps/web)
- **Framework**: React 18+
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State Management**: Redux Toolkit Query (RTK Query)
- **Routing**: React Router v6
- **Port**: 3000

**Key Features:**
- Authentication pages (signin, signup, forgot password)
- File conversion interface
- Internationalization (i18n) - TR/EN
- API integration with backend

**Important Files:**
- `src/app/services/authApi.ts` - Redux RTK Query endpoints
- `src/pages/AuthPage.tsx` - Login/signup
- `src/pages/ForgotPasswordPage.tsx` - Password recovery
- `vite.config.ts` - Dev server config with proxy to backend:3001

### Backend (apps/api)
- **Framework**: NestJS
- **Database**: PostgreSQL via Prisma ORM
- **Authentication**: JWT (access + refresh tokens)
- **Port**: 3001
- **Database URL**: `.env` file (PRISMA_DATABASE_URL)

**Key Modules:**
- `src/auth/` - Authentication (signin, signup, password reset)
- `src/users/` - User management
- `src/files/` - File storage (Vercel Blob)
- `src/mail/` - Email service (SMTP)
- `src/prisma/` - Database service

**Auth Endpoints:**
```
POST /api/auth/sign-up
POST /api/auth/sign-in
POST /api/auth/sign-out
POST /api/auth/forgot-password
POST /api/auth/reset-password
POST /api/auth/verify-email
POST /api/auth/refresh
GET /api/auth/me
```

**Database:**
- Prisma ORM with PostgreSQL
- Location: `apps/api/prisma/schema.prisma`
- Run migrations: `pnpm --filter api prisma migrate dev`
- Open Studio: `pnpm --filter api prisma studio`

### Modal Worker (modal_worker/)
- **Framework**: Modal (Python) — `fastapi`-backed web endpoints, `.map()`/`.spawn()` ile dağıtık çalışan fonksiyonlar
- **Purpose**: PDF → EPUB dönüştürme, plan/map/reduce fazlarına bölünmüş:
  - **Plan** (tek container): PDF indirilir, bölüm haritası + `(start_page, end_page)` chunk listesi (25 sayfalık, `CHUNK_PAGE_SIZE`) hesaplanır.
  - **Map** (`.map()` ile paralel): her container kendi sayfa aralığını Blob'dan kendisi indirip metin/OCR/görsel çıkarır.
  - **Reduce** (tek container, `memory=2048`): sayfa sonuçları bölüm haritasına göre birleştirilip EPUB üretilir, Blob'a yüklenir.
- **Deploy**: `modal deploy modal_worker/main.py` (bkz. yukarıdaki Quick Start)
- **Auth**: Vercel ↔ Modal arası tek paylaşılan sır (`MODAL_WEBHOOK_SECRET`) — Vercel'den gelen isteklerde bearer, Modal'dan Vercel'in webhook'una giden istekte HMAC imzası olarak kullanılır.

**Key Endpoints:**
```
POST /convert - kotayı zaten rezerve etmiş Vercel API'sinden gelir, .spawn() ile arka planda işler, 202 döner
POST /analyze - dönüşümden önce başlık/yazar/bölüm tahmini (senkron, multipart PDF)
```

**Sonuç bildirimi**: `run_pipeline`, tamamlandığında/başarısız olduğunda Vercel'in `POST /api/webhooks/modal-result`'ına HMAC imzalı bir webhook atar (bkz. `apps/api/src/convert/modal-webhook.controller.ts`) — worker artık kendi durumunu tutmuyor, `ConvertJob.status` (Prisma) tek doğruluk kaynağı.

**Sunucu Paketleri** (`modal_worker/main.py`'deki `modal.Image.apt_install(...)` listesi ile senkron tutulmalı — yeni bir dil eklenirse hem oradaki liste hem `modal_worker/converter.py`'deki `LANGUAGE_MAP` güncellenmeli):
- Tesseract OCR binary + `LANGUAGE_MAP`'teki her dil için bir `tesseract-ocr-*` apt paketi (tr/en/de/fr/es/it/pt/nl/ru/ar/pl/sv/el/ja/ko/zh-cn/zh-tw)

## 🌐 Port Configuration

| Service | Port | Running via |
|---------|------|------------|
| Frontend | 3000 | `pnpm dev` or `pnpm --filter web dev` |
| Backend | 3001 | `pnpm dev` or `pnpm --filter api start:dev` |
| Modal worker | — (Modal-hosted URL, pnpm dışı) | `modal serve modal_worker/main.py` (dev) / `modal deploy modal_worker/main.py` (prod) |

**Frontend Proxy Configuration** (`apps/web/vite.config.ts`):
- All `/api/*` requests are proxied to `http://localhost:3001`
- This allows API calls from frontend without CORS issues during dev

## 🔐 Environment Variables

### Backend (apps/api/.env)
```env
PRISMA_DATABASE_URL=postgres://user:pass@host:5432/db
JWT_ACCESS_SECRET=your-secret
JWT_REFRESH_SECRET=your-secret
GOOGLE_CLIENT_ID=your-client-id
APP_URL=http://localhost:3000
SMTP_HOST=smtp-server
SMTP_PORT=587
BLOB_STORE_URL=vercel-blob-url
BLOB_STORE_ID=store-id
BLOB_READ_WRITE_TOKEN=token
MODAL_WEBHOOK_SECRET=shared-secret-with-modal
MODAL_ENDPOINT_URL=https://your-modal-deploy-url
```

### Modal Worker (`modal secret create publisco-secrets ...`)
```env
BLOB_READ_WRITE_TOKEN=token            # aynı token, PDF indirme/EPUB yükleme/silme için
MODAL_WEBHOOK_SECRET=shared-secret-with-modal
VERCEL_WEBHOOK_URL=https://your-api-domain/api/webhooks/modal-result
```

### Frontend (apps/web)
- No .env file needed for dev
- API base URL: configured in `src/app/services/authApi.ts` (baseUrl: '/api')

## 📚 Authentication Flow

1. **Sign Up**: `POST /api/auth/sign-up` → Create user + JWT tokens
2. **Sign In**: `POST /api/auth/sign-in` → Validate credentials + JWT tokens
3. **Forgot Password**: `POST /api/auth/forgot-password` → Send reset email
4. **Reset Password**: `POST /api/auth/reset-password` → Update password
5. **Email Verification**: `POST /api/auth/verify-email` → Verify email token
6. **Refresh**: `POST /api/auth/refresh` → Get new access token with refresh token

## 🔄 Redux Toolkit Query Setup

Frontend uses RTK Query for API calls:
- Store: `src/app/store.ts`
- API hooks: `src/app/services/authApi.ts`
- Configured with `Provider` in `src/main.tsx`

Available hooks:
- `useSignUpMutation()`
- `useSignInMutation()`
- `useForgotPasswordMutation()`
- `useResetPasswordMutation()`

## 📦 Build & Deploy

```bash
# Build all apps
pnpm build

# Build specific app
pnpm --filter api build
pnpm --filter web build
```

## 🧪 Testing

```bash
# Run all tests
pnpm test

# Test specific app
pnpm --filter api test
pnpm --filter web test
```

## 🐛 Common Issues

### "Cannot POST /api/auth/sign-up"
- ✅ Check backend is running on port 3001
- ✅ Check proxy in `vite.config.ts` points to `localhost:3001`
- ✅ Restart frontend dev server after config changes

### Database connection issues
- ✅ Check `PRISMA_DATABASE_URL` in `.env`
- ✅ Run migrations: `pnpm --filter api prisma migrate dev`
- ✅ Verify PostgreSQL is accessible

### CORS errors
- ✅ Backend has CORS enabled in `main.ts` (app.enableCors())
- ✅ Frontend proxy should handle requests (no CORS needed)

### "Failed to fetch" / conversion stuck on PENDING
- ✅ Check `MODAL_ENDPOINT_URL`/`MODAL_WEBHOOK_SECRET` are set in `apps/api/.env` and match the deployed Modal app (`modal deploy modal_worker/main.py`'s output URL + the `publisco-secrets` Modal secret)
- ✅ Check Modal's own logs (`modal app logs publisco-modal-worker`) for the `run_pipeline` function — a webhook failure to `VERCEL_WEBHOOK_URL` leaves the job stuck at `PENDING` in the DB (`ConvertJob.status`)
- ✅ In local dev, Modal can't reach `localhost` for its callback webhook — use `modal serve` + a tunnel (e.g. ngrok) pointing `VERCEL_WEBHOOK_URL` at your local API

## 📝 Important Notes

- **Frontend proxy**: Vite proxies `/api` to backend, so API calls work without CORS
- **Token storage**: Frontend stores JWT in localStorage
- **Email verification**: Required for password reset flow
- **Turbo caching**: Turbo caches builds - use `pnpm turbo build --no-cache` to skip cache
- **Database migrations**: Always run after pulling code if schema changed

## 🚦 Development Workflow

1. Start web + api: `pnpm dev` (see Quick Start above); run `modal serve modal_worker/main.py` separately if touching the conversion pipeline
2. Frontend changes auto-reload
3. Backend changes auto-reload (NestJS watches files)
4. Make API changes → test in Prisma Studio: `pnpm --filter api prisma studio`
5. Update Redux hooks if endpoints change

## 🔁 After Every Task

Before ending a turn that made code changes, do both of these:

1. **NOTES.md** — if the work surfaced a new finding, TODO, bug, or follow-up that isn't already tracked there, add it under the right section (`Yapılacaklar` / `Sorunlar (Buglar)` / `Fikirler`). Skip this if nothing new came up — don't pad the file.
2. **CLAUDE.md → "Sunucu Paketleri" (Modal Worker section)** — if the change added a new *system-level* dependency to `modal_worker/` (an `apt` package in `modal.Image.apt_install(...)`, a new OS binary a Python package shells out to — not a plain `pip_install` package), update that section. A Stop hook (`.claude/hooks/check-worker-deps.sh`) catches the common case (`modal_worker/main.py`/`requirements.txt` changed without `CLAUDE.md`) and will block with a reminder, but it can't tell *why* a package was added — use judgment for the OS-package/system dependency part specifically.

## 📞 Team Notes

- Turbo monorepo handles dependency management
- pnpm is the package manager (faster, workspace-aware)
- Each app has independent `package.json`
- Shared dependencies in root `package.json` when needed
