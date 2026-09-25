# Cara Penggunaan — Hermes Personal AI Agent

Panduan operasional menjalankan Hermes sehari-hari: dari instalasi, menjalankan
lokal, deploy produksi, sampai perawatan. Untuk panduan fitur (chat, template,
notifikasi), lihat [`USER_GUIDE.md`](USER_GUIDE.md). Untuk referensi endpoint,
lihat [`API.md`](API.md).

---

## 1. Yang Perlu Disiapkan

| Kebutuhan | Untuk lokal (Windows) | Untuk produksi (VPS Linux) |
|---|---|---|
| Docker + Docker Compose | [Docker Desktop](https://www.docker.com/products/docker-desktop/) | `docker` + `docker compose plugin` |
| Python | 3.11+ | 3.11+ (hanya bila backend tanpa Docker) |
| Node.js | 20+ | 20+ (hanya bila frontend tanpa Docker) |
| Domain + HTTPS | Tidak perlu (pakai `localhost`) | Wajib (untuk webhook Telegram/WhatsApp) |
| API key model AI | `OPENAI_API_KEY` atau `ANTHROPIC_API_KEY` | Sama |

---

## 2. Menjalankan Secara Lokal (Windows)

Buka **PowerShell** di folder `hermes-personal-ai-agent`.

### 2.1. Siapkan file `.env` (sekali saja)

```powershell
Copy-Item .env.example .env
notepad .env
```

Isi minimal:

```ini
POSTGRES_PASSWORD=isi-password-kuat
REDIS_PASSWORD=isi-password-kuat
JWT_SECRET_KEY=isi-minimal-32-karakter-acak
FIELD_ENCRYPTION_KEY=isi-base64-32-byte
OPENAI_API_KEY=sk-...
```

Buat nilai acak dengan:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### 2.2. Nyalakan database

```powershell
docker compose up -d postgres redis vault
```

### 2.3. Jalankan backend (terminal 1)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Cek: buka `http://localhost:8000/health` → harus `{"status":"ok",...}`.
Dokumentasi API interaktif: `http://localhost:8000/docs`.

### 2.4. Jalankan frontend (terminal 2)

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

Buka `http://localhost:3000` → daftar akun → ikuti wizard **Onboarding**.

### 2.5. Berhenti

- Backend/frontend: `Ctrl+C` di masing-masing terminal.
- Database: `docker compose stop postgres redis vault` (data tersimpan).
- Hapus total termasuk data: `docker compose down -v` ⚠️ (menghapus database).

---

## 3. Menjalankan Produksi (VPS Linux)

Jalankan perintah ini di VPS (butuh domain yang mengarah ke IP VPS).

```bash
cd hermes-personal-ai-agent
cp .env.example .env
nano .env   # isi SEMUA secret, set ENVIRONMENT=production
```

```bash
./deploy.sh init                                  # start DB + migrasi
./deploy.sh certs namadomain.com admin@namadomain.com   # sertifikat TLS
./deploy.sh up                                    # start semua service
./deploy.sh logs                                  # lihat log
```

Setelah up, aplikasi tersedia di `https://namadomain.com`.

### Daftarkan webhook Telegram (sekali saja)

```bash
./deploy.sh webhook <BOT_TOKEN> <TELEGRAM_WEBHOOK_SECRET>
```

Pastikan `TELEGRAM_WEBHOOK_URL=https://namadomain.com/api/webhooks/telegram`
sudah diisi di `.env` sebelum menjalankan perintah di atas.

---

## 4. Penggunaan Sehari-hari

| Aktivitas | Caranya |
|---|---|
| Chat dengan Hermes | Dashboard → **Chat**, atau kirim pesan via Telegram/WhatsApp |
| Perintah cepat | Dashboard → **Template** → **Gunakan** → kirim di Chat |
| Lihat percakapan lama | Dashboard → **Riwayat** → **Lanjutkan di Chat** |
| Buat pengingat | Dashboard → **Notifikasi** (isi pesan + platform + target chat ID) |
| Simpan token layanan | Dashboard → **Onboarding** → Simpan kredensial (terenkripsi) |
| Ekspor/hapus data | Dashboard → **Privasi** |

Contoh perintah yang bisa dicoba:

- `Halo, siapa kamu?`
- `Cari 5 berita terbaru tentang AI dan rangkum`
- `Ingatkan saya meeting besok jam 10` (perlu target chat ID di Notifikasi)
- `Cek uptime website https://example.com`
- `Cek status server 192.168.1.10` (perlu whitelist SSH + kredensial)

---

## 5. Perawatan

```bash
# Jalankan tes backend (55+ tes: scrubbing, kripto, tools, webhook)
cd backend && pytest

# Lint backend
ruff check app tests

# Typecheck + build frontend
cd frontend && npm run typecheck && npm run build

# Migrasi database setelah update kode
./deploy.sh migrate        # produksi
alembic upgrade head       # lokal (dari folder backend, venv aktif)

# Backup database (produksi)
docker compose exec postgres pg_dump -U hermes hermes > backup-$(date +%F).sql
```

---

## 6. Troubleshooting

| Gejala | Penyebab umum | Solusi |
|---|---|---|
| Balasan "asisten belum dikonfigurasi" | `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` kosong | Isi di `.env`, restart backend |
| Telegram tidak membalas | Webhook belum terdaftar / secret salah | Jalankan `./deploy.sh webhook`, cek `TELEGRAM_WEBHOOK_SECRET` |
| WhatsApp Twilio 403 | Signature tidak valid | Pastikan `TWILIO_AUTH_TOKEN` benar dan URL webhook persis |
| Perintah SSH ditolak | Di luar whitelist | Tambahkan prefix ke `SSH_COMMAND_WHITELIST` |
| Pencarian gagal | `SEARCH_PROVIDER=none` atau key kosong | Set `serpapi`/`brave` + API key |
| Frontend "Gagal menghubungi asisten" | Backend mati / URL salah | Cek `http://localhost:8000/health` dan `NEXT_PUBLIC_API_URL` |
| Login 429 | Kena rate limit auth (5/menit) | Tunggu 1 menit, coba lagi |
| Alembic error koneksi | Postgres belum siap | `docker compose up -d postgres`, tunggu 5 detik, ulangi |

---

## 7. Keamanan Praktis

- **Jangan pernah** commit file `.env` atau menempel token di chat/issue.
- Kata sandi, NIK, dan nomor kartu otomatis disensor — tapi tetap hindari
  mengirimnya bila tidak perlu.
- Cadangkan database berkala (lihat Backup di atas) dan simpan di tempat aman.
- Perbarui dependensi secara berkala: `pip install -U -r requirements.txt`
  (backend) dan `npm update` (frontend), lalu jalankan tes sebelum deploy.
