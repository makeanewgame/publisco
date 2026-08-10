# publisco - Turbo Monorepo Project Guide

## 🏗️ Project Structure

```
publisco/
├── apps/
│   ├── web/          # React + Vite frontend (port 3000)
│   ├── api/          # NestJS backend (port 3001)
│   └── worker/       # FastAPI worker service (port 3002)
├── pnpm-workspace.yaml
├── turbo.json
└── package.json
```

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- pnpm (package manager)
- Python 3.10+ (for FastAPI worker — `apps/worker/requirements.txt` pins `fastapi==0.141.1`, which requires 3.10+; if your system `python3` is older, install an isolated version, e.g. `brew install python@3.12`, and build the worker's venv with that binary instead of the system one — see `apps/worker/README.md`)

### Running the Project

**Option 1: All three at once**
```bash
pnpm dev
```
`apps/worker` has a `package.json` with a `dev` script (`.venv/bin/uvicorn ...`), so it's a pnpm/Turbo workspace member too — this command starts all three apps in parallel via Turbo:
- Frontend: http://localhost:3000
- Backend API: http://localhost:3001
- Worker: http://localhost:3002

Requires the worker's venv to already exist (see Prerequisites above) — if it's missing, the `worker#dev` task fails fast with a message pointing to `apps/worker/README.md` instead of starting.

**Option 2: Individual services**
```bash
# Frontend only
pnpm --filter web dev

# Backend only
pnpm --filter api start:dev

# Worker only
pnpm --filter worker dev
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

### Worker (apps/worker)
- **Framework**: FastAPI
- **Purpose**: PDF to EPUB conversion
- **Port**: 3002

**Key Endpoints:**
```
GET /health
POST /convert - PDF to EPUB conversion
```

## 🌐 Port Configuration

| Service | Port | Running via |
|---------|------|------------|
| Frontend | 3000 | `pnpm dev` or `pnpm --filter web dev` |
| Backend | 3001 | `pnpm dev` or `pnpm --filter api start:dev` |
| Worker | 3002 | `pnpm dev` or `pnpm --filter worker dev` |

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

### "Failed to fetch" / `ERR_CONNECTION_REFUSED` on `/convert`
- ✅ Check the worker is actually running — `pnpm dev` now starts it too (see Quick Start), but if its venv is missing the `worker#dev` task fails fast instead of serving
- ✅ Check the worker's venv exists and was built with Python 3.10+ (`python3 --version` inside the venv) — see Prerequisites above; if missing, run `pnpm --filter worker dev` directly to see the setup error

## 📝 Important Notes

- **Frontend proxy**: Vite proxies `/api` to backend, so API calls work without CORS
- **Token storage**: Frontend stores JWT in localStorage
- **Email verification**: Required for password reset flow
- **Turbo caching**: Turbo caches builds - use `pnpm turbo build --no-cache` to skip cache
- **Database migrations**: Always run after pulling code if schema changed

## 🚦 Development Workflow

1. Start all three: `pnpm dev` (frontend, backend, and worker — see Quick Start above)
2. Frontend changes auto-reload
3. Backend changes auto-reload (NestJS watches files)
4. Make API changes → test in Prisma Studio: `pnpm --filter api prisma studio`
5. Update Redux hooks if endpoints change

## 🔁 After Every Task

Before ending a turn that made code changes, do both of these:

1. **NOTES.md** — if the work surfaced a new finding, TODO, bug, or follow-up that isn't already tracked there, add it under the right section (`Yapılacaklar` / `Sorunlar (Buglar)` / `Fikirler`). Skip this if nothing new came up — don't pad the file.
2. **apps/worker/README.md → "Sunucu Paketleri"** — if the change added a new *system-level* dependency to the worker (an `apt`/`brew` package, a new OS binary a Python package shells out to — not a plain pip package), update that section. A Stop hook (`.claude/hooks/check-worker-deps.sh`) catches the common case (`requirements*.txt` changed without `README.md`) and will block with a reminder, but it can't tell *why* a package was added — use judgment for the OS-package/system dependency part specifically.

## 📞 Team Notes

- Turbo monorepo handles dependency management
- pnpm is the package manager (faster, workspace-aware)
- Each app has independent `package.json`
- Shared dependencies in root `package.json` when needed
