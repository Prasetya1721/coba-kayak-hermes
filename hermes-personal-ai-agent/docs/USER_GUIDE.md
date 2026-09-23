# Panduan Pengguna — Hermes Personal AI Agent

Selamat! Hermes adalah asisten pribadi AI yang bekerja 24/7 dan bisa dihubungi dari
**Telegram** atau **WhatsApp**. Panduan ini ramah pemula: ikuti langkahnya dan Anda
bisa mulai dalam waktu kurang dari 10 menit.

---

## 1. Kenalan dengan Hermes

Hermes bisa:

- **Menjawab pertanyaan** apa saja (umum, teknis, kontekstual).
- **Mengelola perangkat** — cek status server, restart service (melalui perintah terbatas).
- **Mengelola web** — deploy ke Vercel, update repository GitHub, cek uptime.
- **Mengelola notifikasi** — kirim & jadwalkan pengingat.
- **Mencari informasi** — cari di web lalu merangkum hasilnya.

> **Penting:** Anda berbicara dengan AI. Jawaban bisa keliru. Selalu periksa
> informasi penting sebelum bertindak.

---

## 2. Membuat Akun

1. Buka alamat dashboard Hermes (mis. `https://domain-anda`).
2. Klik **Mulai Gratis** dan isi username, email, serta password.
3. Centang **Persetujuan (UU PDP)**. Ini memberi izin Hermes memproses isi
   percakapan Anda untuk keperluan operasional saja.
4. Klik **Daftar**, lalu masuk.

---

## 3. Onboarding (Wizard)

Setelah masuk, buka menu **Onboarding**. Anda akan melihat daftar langkah:

| Langkah | Apa yang dilakukan |
| --- | --- |
| Akun dibuat | Otomatis selesai. |
| Persetujuan UU PDP | Otomatis selesai. |
| Atur API key model AI | Hubungi admin untuk mengisi `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`. |
| Hubungkan Telegram | Lihat bagian 4. |
| Hubungkan WhatsApp | Lihat bagian 5. |
| Pilih template | Buka menu **Template**. |
| Buat notifikasi | Buka menu **Notifikasi**. |

Progress bar di atas menunjukkan seberapa jauh Anda.

---

## 4. Menghubungkan Telegram

1. Buka Telegram, cari **@BotFather**.
2. Kirim `/newbot`, ikuti langkahnya, dan salin **token** yang diberikan.
3. Serahkan token ke admin/operator untuk diisi sebagai `TELEGRAM_BOT_TOKEN`.
4. Setelah domain HTTPS aktif, admin mendaftarkan webhook (sekali saja):
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://domain-anda/api/webhooks/telegram
   ```
5. Cari bot Anda di Telegram dan kirim pesan seperti `halo`. Hermes akan membalas.

---

## 5. Menghubungkan WhatsApp

**Cara resmi (Twilio):**

1. Buat akun Twilio, aktifkan produk WhatsApp.
2. Salin **Account SID**, **Auth Token**, dan nomor pengirim ke konfigurasi.
3. Atur webhook Twilio ke `https://domain-anda/api/webhooks/whatsapp`.
4. Kirim pesan uji dari nomor WhatsApp Anda.

**Cara self-hosted (Baileys):**

1. Jalankan gateway Baileys (butuh scan QR sekali).
2. Set `WHATSAPP_PROVIDER=baileys` dan alamat gateway.
3. Gunakan nomor khusus. ⚠️ WhatsApp dapat memblokir nomor yang terindikasi otomatis.

---

## 6. Memakai Template

Menu **Template** berisi perintah siap pakai, misalnya:

- *"Buat landing page sederhana untuk produk {nama}"*
- *"Cek uptime website saya di {url}"*
- *"Ingatkan saya meeting besok jam {jam}"*
- *"Cari 5 berita terbaru tentang {topik} dan rangkum"*

Klik **Gunakan** untuk mengisi kotak chat, ganti bagian `{...}` dengan data Anda,
lalu kirim. Anda juga bisa membuat template sendiri dengan tombol **Template baru**.

---

## 7. Menjadwalkan Notifikasi

1. Buka menu **Notifikasi**.
2. Isi pesan, pilih platform (Telegram/WhatsApp), dan isi target chat ID.
3. Pilih:
   - **Cron** untuk berulang, mis. `0 9 * * *` (setiap hari jam 09:00), atau
   - **Sekali jalan** dengan memilih tanggal & waktu.
4. Klik **Jadwalkan**. Notifikasi akan dikirim otomatis oleh penjadwal.

Anda bisa menonaktifkan sementara (tombol daya) atau menghapusnya kapan saja.

---

## 8. Chat & Riwayat dari Dashboard

Menu **Chat** memungkinkan Anda mengobrol langsung dari browser. Menu **Riwayat**
menampilkan semua percakapan (Telegram, WhatsApp, dan web) dengan tombol
**Lanjutkan di Chat** untuk membuka kembali sesi lama. Anda juga bisa menghapus
sesi per sesi. Perhatikan:

- Bila Anda menulis data sensitif (kartu, NIK, password), Hermes otomatis
  **menyensornya** dan menampilkan peringatan.
- Tekan **Enter** untuk mengirim, **Shift+Enter** untuk baris baru.

---

## 9. Keamanan Data Anda

Buka menu **Privasi** untuk:

- **Ekspor data** — unduh seluruh data Anda dalam format JSON.
- **Hapus riwayat** — menghapus semua chat, template, notifikasi, dan kredensial.
- **Hapus akun** — menghapus akun beserta seluruh data secara permanen.

Prinsip yang Hermes pegang:

- Isi percakapan disimpan **terenkripsi AES-256**.
- Kredensial layanan dikelola oleh sistem manajemen kunci (Vault).
- Identitas pribadi disimpan terpisah dari data operasional.
- Data **tidak** dipakai untuk melatih model pihak ketiga.

---

## 10. Tips & Pemecahan Masalah

- **Hermes tidak membalas di Telegram/WhatsApp** — pastikan webhook sudah
  terdaftar dan `TELEGRAM_BOT_TOKEN` benar.
- **Balasan "asisten belum dikonfigurasi"** — API key model AI belum diisi.
- **Perintah server ditolak** — perintah harus ada di whitelist; coba `uptime`,
  `df -h`, atau `pm2 status`.
- **Pencarian gagal** — provider web search belum diset (`SEPAPI`/`Brave`).

Selamat! Anda siap memakai Hermes. Mulailah dengan sapaan sederhana: **"halo"**.
