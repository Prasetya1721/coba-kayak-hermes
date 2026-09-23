"use client";

import { useState } from "react";
import { AlertTriangle, Download, Loader2, ShieldCheck, Trash2, UserX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";

const CONFIRM_TEXT = "HAPUS";

export default function PrivacyPage() {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");

  async function exportData() {
    setBusy("export");
    setError(null);
    try {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hermes-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage("Data berhasil diekspor.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal mengekspor data.");
    } finally {
      setBusy(null);
    }
  }

  async function deleteData() {
    setBusy("data");
    setError(null);
    try {
      const res = await api.deleteAllData();
      setMessage(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menghapus data.");
    } finally {
      setBusy(null);
    }
  }

  async function deleteAccount() {
    if (confirm !== CONFIRM_TEXT) {
      setError(`Ketik "${CONFIRM_TEXT}" untuk mengonfirmasi penghapusan akun.`);
      return;
    }
    setBusy("account");
    setError(null);
    try {
      await api.deleteAccount();
      api.logout();
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menghapus akun.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold">Privasi &amp; Data</h1>
        <p className="text-xs text-muted-foreground">
          Kontrol penuh atas data Anda sesuai UU PDP (hak akses &amp; hak untuk dilupakan).
        </p>
      </div>

      {message && (
        <p className="mb-4 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600">
          {message}
        </p>
      )}
      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4 text-primary" /> Ringkasan kebijakan
            </CardTitle>
            <CardDescription>Sederhana, transparan, dan dapat dikontrol.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>• Anda berinteraksi dengan AI. Respons dapat keliru.</p>
            <p>• Isi percakapan disimpan terenkripsi AES-256.</p>
            <p>• Data sensitif (password, kartu, NIK) disensor sebelum diproses.</p>
            <p>• Identitas pribadi disimpan terpisah dari data operasional.</p>
            <p>• Data tidak digunakan untuk melatih model pihak ketiga.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Download className="h-4 w-4 text-primary" /> Ekspor data
            </CardTitle>
            <CardDescription>Unduh seluruh data Anda dalam format JSON.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={exportData} disabled={busy === "export"}>
              {busy === "export" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Ekspor data saya
            </Button>
          </CardContent>
        </Card>

        <Card className="border-amber-500/40">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Trash2 className="h-4 w-4 text-amber-600" /> Hapus riwayat data
            </CardTitle>
            <CardDescription>
              Menghapus semua riwayat chat, template, notifikasi, dan kredensial. Akun tetap aktif.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={deleteData} disabled={busy === "data"}>
              {busy === "data" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Hapus semua data
            </Button>
          </CardContent>
        </Card>

        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserX className="h-4 w-4 text-destructive" /> Hapus akun
            </CardTitle>
            <CardDescription>
              Menghapus akun secara permanen beserta semua data terkait. Tidak dapat dibatalkan.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label>
                Ketik &quot;{CONFIRM_TEXT}&quot; untuk konfirmasi
              </Label>
              <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            <Button variant="destructive" onClick={deleteAccount} disabled={busy === "account"}>
              {busy === "account" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <AlertTriangle className="h-4 w-4" />
              )}
              Hapus akun permanen
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
