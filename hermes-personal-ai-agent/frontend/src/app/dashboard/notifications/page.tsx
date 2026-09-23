"use client";

import { useEffect, useState } from "react";
import { Bell, Loader2, Plus, Power, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import type { Notification } from "@/lib/types";
import { formatDateTime, formatRelative } from "@/lib/utils";

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    message: "",
    platform: "telegram" as "telegram" | "whatsapp",
    schedule_cron: "0 9 * * *",
    run_at: "",
    target_chat_id: "",
  });

  async function load() {
    setLoading(true);
    try {
      setItems(await api.listNotifications());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat notifikasi.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body: Parameters<typeof api.createNotification>[0] = {
        message: form.message,
        platform: form.platform,
        target_chat_id: form.target_chat_id || undefined,
      };
      if (form.run_at) body.run_at = new Date(form.run_at).toISOString();
      else body.schedule_cron = form.schedule_cron;
      await api.createNotification(body);
      setForm({ ...form, message: "", run_at: "" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal membuat notifikasi.");
    }
  }

  async function toggle(id: string) {
    await api.toggleNotification(id);
    await load();
  }

  async function remove(id: string) {
    await api.deleteNotification(id);
    await load();
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold">Notifikasi Terjadwal</h1>
        <p className="text-xs text-muted-foreground">
          Kirim pengingat otomatis ke Telegram atau WhatsApp. Isi target chat untuk pengiriman.
        </p>
      </div>

      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="h-4 w-4 text-primary" /> Buat notifikasi
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="space-y-4">
            <div className="space-y-2">
              <Label>Pesan</Label>
              <Input
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="Contoh: Ingatkan meeting jam 10"
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label>Platform</Label>
                <select
                  value={form.platform}
                  onChange={(e) =>
                    setForm({ ...form, platform: e.target.value as "telegram" | "whatsapp" })
                  }
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="telegram">Telegram</option>
                  <option value="whatsapp">WhatsApp</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Cron (berulang)</Label>
                <Input
                  value={form.schedule_cron}
                  onChange={(e) => setForm({ ...form, schedule_cron: e.target.value })}
                  placeholder="0 9 * * *"
                  disabled={!!form.run_at}
                />
              </div>
              <div className="space-y-2">
                <Label>Sekali jalan (opsional)</Label>
                <Input
                  type="datetime-local"
                  value={form.run_at}
                  onChange={(e) => setForm({ ...form, run_at: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Target chat ID</Label>
              <Input
                value={form.target_chat_id}
                onChange={(e) => setForm({ ...form, target_chat_id: e.target.value })}
                placeholder="Telegram chat id atau nomor WhatsApp"
              />
            </div>
            <Button type="submit">Jadwalkan</Button>
          </form>
        </CardContent>
      </Card>

      {loading ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : items.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Belum ada notifikasi terjadwal.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((n) => (
            <Card key={n.id}>
              <CardContent className="flex flex-wrap items-center gap-3 p-4">
                <Bell className="h-5 w-5 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{n.message}</p>
                  <p className="text-xs text-muted-foreground">
                    {n.platform} · {n.schedule_cron ? `cron: ${n.schedule_cron}` : "sekali jalan"} ·{" "}
                    berikutnya {formatDateTime(n.next_run)} ({formatRelative(n.next_run)})
                  </p>
                </div>
                <Badge
                  className={
                    n.active
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600"
                      : "border-muted-foreground/30 bg-muted text-muted-foreground"
                  }
                >
                  {n.active ? "Aktif" : "Nonaktif"}
                </Badge>
                <Button size="sm" variant="ghost" onClick={() => toggle(n.id)}>
                  <Power className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => remove(n.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
