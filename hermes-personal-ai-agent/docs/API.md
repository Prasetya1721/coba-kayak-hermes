# API Reference — Hermes Personal AI Agent

Base URL: `http://localhost:8000` (dev) · `/api` adalah prefix semua route aplikasi.
Autentikasi: **Bearer JWT** pada header `Authorization: Bearer <access_token>`.

Format error standar:

```json
{ "detail": "Pesan kesalahan.", "request_id": "uuid" }
```

---

## Meta

| Method | Path | Deskripsi |
| --- | --- | --- |
| GET | `/health` | Cek kesehatan layanan. |
| GET | `/docs` | Swagger UI (nonaktif di produksi). |

---

## Auth

### POST `/api/auth/register`
Buat akun. **Consent wajib.**

```json
{
  "username": "budi",
  "email": "budi@example.com",
  "password": "rahasia123",
  "display_name": "Budi",
  "timezone": "Asia/Jakarta",
  "consent": true
}
```

Respons `201`: objek user (tanpa password).

### POST `/api/auth/login`
```json
{ "username": "budi", "password": "rahasia123" }
```
Respons `200`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST `/api/auth/refresh`
```json
{ "refresh_token": "eyJ..." }
```
Mengembalikan pasangan token baru.

### GET `/api/auth/me`
Mengembalikan user yang sedang login.

### GET / PUT `/api/auth/profile`
`GET` mengembalikan profil; `PUT` memperbarui `display_name`, `phone_number`, `timezone`.

---

## Chat

### POST `/api/chat/message`
Kirim pesan ke agen (kanal web). Data sensitif disensor sebelum diproses.

```json
{ "message": "Cek uptime example.com", "session_id": null }
```

Respons:
```json
{
  "session_id": "uuid",
  "reply": "...",
  "scrubbed": true,
  "detections": ["credit_card"]
}
```

### GET `/api/chat/sessions`
Daftar sesi milik pengguna.

### GET `/api/chat/sessions/{session_id}`
Riwayat pesan terdekripsi (server-side) dalam urutan kronologis.

### DELETE `/api/chat/sessions/{session_id}`
Menghapus seluruh log pada sesi tersebut.

---

## Templates

| Method | Path | Deskripsi |
| --- | --- | --- |
| GET | `/api/templates?category=` | Daftar template (bawaan + milik pengguna). |
| POST | `/api/templates` | Buat template. |
| PUT | `/api/templates/{id}` | Perbarui template milik pengguna. |
| DELETE | `/api/templates/{id}` | Hapus template milik pengguna. |

Body buat/perbarui:
```json
{
  "title": "Cek uptime",
  "description": "Periksa status situs",
  "command_pattern": "Cek uptime website {url}",
  "category": "web"
}
```

---

## Notifications

| Method | Path | Deskripsi |
| --- | --- | --- |
| GET | `/api/notifications?active_only=` | Daftar notifikasi. |
| POST | `/api/notifications` | Buat notifikasi (cron atau sekali jalan). |
| POST | `/api/notifications/{id}/toggle` | Aktif/nonaktif. |
| DELETE | `/api/notifications/{id}` | Hapus. |

Body:
```json
{
  "message": "Meeting jam 10",
  "platform": "telegram",
  "schedule_cron": "0 9 * * *",
  "target_chat_id": "123456789"
}
```
Gunakan `run_at` (ISO 8601) sebagai alternatif `schedule_cron` untuk sekali jalan.

---

## Credentials

| Method | Path | Deskripsi |
| --- | --- | --- |
| GET | `/api/credentials` | Daftar layanan (metadata; token tidak pernah dikembalikan). |
| POST | `/api/credentials` | Simpan token terenkripsi. |
| DELETE | `/api/credentials/{service_name}` | Hapus kredensial. |

Body POST:
```json
{ "service_name": "github_token", "token": "ghp_..." }
```

---

## Onboarding

### GET `/api/onboarding/status`
```json
{
  "completed": false,
  "steps": { "account_created": true, "llm_configured": false },
  "next_step": "llm_configured"
}
```

---

## Privacy (UU PDP)

| Method | Path | Deskripsi |
| --- | --- | --- |
| GET | `/api/privacy/export` | Ekspor seluruh data pengguna (JSON). |
| DELETE | `/api/privacy/data` | Hapus riwayat chat, template, notifikasi, kredensial. |
| DELETE | `/api/privacy/account` | Hapus akun beserta seluruh data (permanen). |

---

## Webhooks (publik, tanpa JWT)

### POST `/api/webhooks/telegram`
Menerima update Telegram. Header `X-Telegram-Bot-Api-Secret-Token` diverifikasi
bila `TELEGRAM_WEBHOOK_SECRET` diset.

### GET `/api/webhooks/telegram/setup`
Menampilkan URL `setWebhook` yang siap dipakai.

### POST `/api/webhooks/whatsapp`
Menerima payload Twilio (form) atau Baileys (JSON). Signature Twilio diverifikasi
bila `TWILIO_AUTH_TOKEN` diset.

Keduanya mengembalikan `200` cepat; balasan agen dikirim asinkron ke platform.

---

## Rate Limiting

- API: `RATE_LIMIT_PER_MINUTE` (default 60/menit) via slowapi.
- Webhook: `RATE_LIMIT_WEBHOOK_PER_MINUTE` (default 120/menit).
- Nginx menambah batas `api_limit` (30 r/s) dan `webhook_limit` (60 r/s).

## Kode Status

| Kode | Arti |
| --- | --- |
| 200 | Sukses. |
| 201 | Dibuat. |
| 204 | Sukses tanpa isi (delete). |
| 400 | Permintaan tidak valid (mis. consent belum diberikan). |
| 401 | Token tidak ada/invalid. |
| 403 | Ditolak (secret/signature webhook salah). |
| 404 | Sumber daya tidak ditemukan. |
| 409 | Konflik (username/email sudah ada). |
| 429 | Melebihi batas permintaan. |
| 500 | Kesalahan server. |
