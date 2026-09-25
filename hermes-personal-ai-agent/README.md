# Hermes Personal AI Agent (HPA)

Asisten pribadi AI 24/7 yang berjalan di belakang layar dan dapat dihubungkan ke
**Telegram** dan **WhatsApp** sebagai antarmuka utama. Dirancang untuk penggunaan
pribadi (*single-user*) untuk **vibe coding**, **pengelolaan web**, **notifikasi**,
dan **pencarian informasi** — dengan privasi dan keamanan sebagai prioritas.

> **Transparansi AI:** Anda berinteraksi dengan model bahasa. Respons dapat keliru.
> Data percakapan disimpan terenkripsi (AES-256) dan dapat dihapus kapan saja.

---

## Daftar Isi

- [Arsitektur](#arsitektur)
- [Struktur Proyek](#struktur-proyek)
- [Menjalankan Secara Lokal](#menjalankan-secara-lokal)
- [Konfigurasi](#konfigurasi)
- [Menghubungkan Telegram](#menghubungkan-telegram)
- [Menghubungkan WhatsApp](#menghubungkan-whatsapp)
- [Keamanan & Privasi](#keamanan--privasi)
- [Pengujian](#pengujian)
- [Deployment Produksi](#deployment-produksi)
- [Dokumentasi Lanjutan](#dokumentasi-lanjutan)

---

## Arsitektur

```
                 ┌─────────────┐        ┌──────────────────────┐
   Telegram ◄────┤  Gateway    ├───────►│  FastAPI (backend)   │
   WhatsApp ◄────┤  webhooks   │        │  routes → services   │
                 └─────────────┘        │        → repositories│
                                        │                      │
   Browser  ───► Next.js dashboard ───► │  AI Agent (LangChain)│
                                        │   tools: search/ssh/ │
                                        │   deploy/schedule    │
                                        └───────┬──────────────┘
                                                │
                      ┌─────────────────────────┼──────────────────────┐
                      ▼                         ▼                      ▼
                ┌───────────┐            ┌───────────┐          ┌───────────┐
                │PostgreSQL │            │  Redis    │          │  Vault    │
                │ AES-256   │            │ queue/    │          │  (KMS)    │
                │ (logs)    │            │ session   │          │           │
                └───────────┘            └───────────┘          └───────────┘
```

- **Frontend** — Next.js 14 (App Router), TypeScript, Tailwind, komponen ala shadcn/ui.
- **Backend** — FastAPI (Python 3.11), clean architecture `routes → services → repositories`.
- **Database** — PostgreSQL 16 (+ `pgcrypto`), Redis untuk antrian/sesi.
- **AI Engine** — LangChain dengan GPT-4o atau Claude 3.5 Sonnet (function calling).
- **Messaging** — Telegram Bot API; WhatsApp via Twilio (resmi) atau Baileys (self-hosted).
- **KMS** — HashiCorp Vault untuk enkripsi kredensial (fallback AES-256 lokal untuk dev).

## Struktur Proyek

```
hermes-personal-ai-agent/
├── backend/
│   ├── app/
│   │   ├── api/            # routes + dependencies (auth)
│   │   ├── core/           # config, logging, security (JWT), crypto (AES-256/Vault)
│   │   ├── db/             # models, session, seed
│   │   ├── middleware/     # scrubbing + http hardening
│   │   ├── repositories/   # akses data (clean architecture)
│   │   ├── schemas/        # Pydantic request/response
│   │   └── services/
│   │       ├── agent/      # LLM core, tool registry, tools/*
│   │       ├── gateways/   # sender (Telegram/WA), processor webhook
│   │       └── ...         # auth_service, notification_scheduler
│   ├── alembic/            # migrasi database
│   ├── initdb/             # ekstensi pgcrypto saat inisialisasi
│   ├── tests/              # unit + integration tests
│   └── Dockerfile
├── frontend/
│   ├── src/app/            # landing, (auth), dashboard/*
│   ├── src/components/ui/  # primitive UI
│   ├── src/context/        # AuthContext
│   ├── src/lib/            # API client + tipe + util
│   └── Dockerfile
├── docker/nginx/           # reverse proxy + template TLS
├── docker-compose.yml
├── deploy.sh               # helper bring-up produksi
├── .env.example
└── README.md
```

## Menjalankan Secara Lokal

### 1. Prasyarat

- Docker + Docker Compose
- Node.js 20 (untuk frontend)
- Python 3.11 (untuk backend bila dijalankan tanpa Docker)

### 2. Siapkan environment

```bash
cp .env.example .env
# Isi minimal: POSTGRES_PASSWORD, REDIS_PASSWORD, JWT_SECRET_KEY,
# FIELD_ENCRYPTION_KEY, dan salah satu OPENAI_API_KEY / ANTHROPIC_API_KEY.
```

Hasilkan secret yang kuat:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                 # JWT
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())" # FIELD key
```

### 3. Nyalakan infrastruktur

```bash
docker compose up -d postgres redis vault
```

### 4. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .\.venv\Scripts\activate
# Linux/mac: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API tersedia di `http://localhost:8000` (dokum: `/docs`, health: `/health`).

### 5. Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Buka `http://localhost:3000`, daftar akun, lalu ikuti wizard onboarding.

## Konfigurasi

Semua rahasia berasal dari environment (lihat `.env.example`). Poin penting:

| Variabel | Fungsi |
| --- | --- |
| `LLM_PROVIDER` | `openai` atau `anthropic` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Kunci model AI |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram |
| `TELEGRAM_WEBHOOK_URL` | URL HTTPS webhook publik |
| `TELEGRAM_WEBHOOK_SECRET` | Verifikasi asal webhook |
| `WHATSAPP_PROVIDER` | `twilio`, `baileys`, atau `none` |
| `SEARCH_PROVIDER` | `serpapi`, `brave`, atau `none` |
| `SSH_COMMAND_WHITELIST` | Prefix perintah SSH yang diizinkan |
| `GITHUB_TOKEN` / `VERCEL_TOKEN` | Tool web management |
| `VAULT_ADDR` / `VAULT_TOKEN` | KMS untuk kredensial |
| `SCHEDULER_*` | Penjadwal notifikasi |

> Di produksi, `assert_production_safety()` akan menolak start bila ada nilai
> default yang tidak aman (JWT lemah, `DEBUG=true`, field key kosong).

## Menghubungkan Telegram

1. Buat bot via [@BotFather](https://t.me/BotFather), salin token ke `TELEGRAM_BOT_TOKEN`.
2. Set `TELEGRAM_WEBHOOK_URL` ke `https://domain-anda/api/webhooks/telegram`.
3. Daftarkan webhook sekali:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://domain-anda/api/webhooks/telegram" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Atau gunakan `./deploy.sh webhook <TOKEN> <SECRET>`.

## Menghubungkan WhatsApp

**Opsi A — Twilio (resmi, direkomendasikan).**
Set `WHATSAPP_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_WHATSAPP_FROM`, lalu arahkan webhook Twilio ke
`https://domain-anda/api/webhooks/whatsapp`. Signature Twilio diverifikasi otomatis.

**Opsi B — Baileys (self-hosted, gratis).**
Jalankan gateway Baileys yang mengekspos `POST /send` dan meneruskan pesan masuk
ke `/api/webhooks/whatsapp`. Set `WHATSAPP_PROVIDER=baileys`,
`BAILEYS_GATEWAY_URL`, dan `BAILEYS_GATEWAY_TOKEN`.
⚠️ Berisiko pemblokiran akun — gunakan nomor khusus.

## Keamanan & Privasi

- **Penyensoran otomatis** sebelum data diproses/disimpan: kartu kredit (Luhn),
  NIK 16 digit, password/token/secret, header Authorization, private key, email &
  nomor HP (parsial). Lihat `backend/app/middleware/scrubbing.py`.
- **Enkripsi at rest**: isi `chat_logs` disimpan sebagai ciphertext AES-256-GCM
  (nonce acak + autentikasi tag). Kredensial layanan dienkripsi via Vault transmig
  atau kunci lokal (`FIELD_ENCRYPTION_KEY`).
- **In transit**: HTTPS/TLS 1.2+ via Nginx + Certbot.
- **Kepatuhan UU PDP**: consent wajib saat registrasi, endpoint ekspor data
  (`GET /api/privacy/export`), hapus riwayat (`DELETE /api/privacy/data`), dan
  hapus akun (`DELETE /api/privacy/account`).
- **Hardening**: security headers, CORS terbatas, rate limiting (slowapi + Nginx),
  whitelist perintah SSH, verifikasi signature webhook.
- **Logging tanpa data sensitif**: formatter men-scrub ulang setiap nilai string.

## Pengujian

```bash
cd backend
pytest                      # 55 tests: scrubbing, crypto/auth, tools, webhooks
ruff check app tests        # lint
```

Contoh cakupan:

- **Scrubbing** — kartu kredit, NIK, password, token, email/HP, idempotensi, rekursif.
- **Kripto & Auth** — roundtrip AES-256, deteksi tampering, hash password, JWT.
- **Tools** — whitelist SSH & penolakan metakarakter, validasi cron, guard token.
- **Webhooks** — verifikasi secret Telegram, signature Twilio, parsing payload.

## Deployment Produksi

```bash
cp .env.example .env      # isi semua rahasia, set ENVIRONMENT=production
./deploy.sh init          # build + migrasi + start layanan dasar
./deploy.sh certs example.com admin@example.com   # TLS Let's Encrypt
./deploy.sh up            # nyalakan stack produksi (nginx + certbot)
./deploy.sh logs          # ikuti log
```

Stack produksi: `frontend` + `backend` + `nginx` (TLS, rate limit) + `certbot`
(renew otomatis tiap 12 jam). Backend & frontend hanya terikat ke `127.0.0.1`;
Nginx mengekspos 80/443.

## Dokumentasi Lanjutan

- [`docs/CARA_PENGGUNAAN.md`](docs/CARA_PENGGUNAAN.md) — cara penggunaan operasional (instalasi, run lokal/produksi, perawatan).
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — panduan fitur untuk pengguna (pemula).
- [`docs/API.md`](docs/API.md) — referensi API backend.
- `backend/alembic/versions/0001_init.py` — skema database lengkap.
