"use client";

import { useEffect, useState } from "react";
import { Brain, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import type { MemoryItem } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const KEY_LABELS: Record<string, string> = {
  nama: "Nama",
  ulang_tahun: "Ulang tahun",
  kota: "Kota",
  pekerjaan: "Pekerjaan",
  preferensi: "Kesukaan",
  perangkat: "Perangkat",
  proyek: "Proyek",
  kode: "Preferensi kode",
  catatan: "Catatan",
};

function scopeLabel(scope: string | undefined): string | null {
  if (!scope || scope === "global") return null;
  if (scope === "kode") return "Kode";
  if (scope.startsWith("proyek:")) return `Proyek ${scope.slice(7).toUpperCase()}`;
  return scope;
}

export default function MemoriesPage() {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState({ key: "catatan", value: "" });

  async function load() {
    setLoading(true);
    try {
      setItems(await api.listMemories());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat ingatan.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createMemory(draft);
      setDraft({ key: "catatan", value: "" });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menyimpan ingatan.");
    }
  }

  async function remove(id: string) {
    await api.deleteMemory(id);
    await load();
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Ingatan Stella</h1>
          <p className="text-xs text-muted-foreground">
            Hal-hal yang Stella ingat tentangmu. Bisa juga bilang langsung di chat:
            &quot;ingat ya, ...&quot; atau &quot;lupakan ...&quot;.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" /> Ingatan baru
        </Button>
      </div>

      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {showForm && (
        <Card className="mb-6 animate-slide-up">
          <CardHeader>
            <CardTitle>Tambah ingatan</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-4">
              <div className="space-y-2">
                <Label>Kategori</Label>
                <select
                  value={draft.key}
                  onChange={(e) => setDraft({ ...draft, key: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(KEY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label>Isi ingatan</Label>
                <Input
                  value={draft.value}
                  onChange={(e) => setDraft({ ...draft, value: e.target.value })}
                  placeholder="Contoh: Prasetya, suka kopi tubruk"
                  required
                />
              </div>
              <div className="flex gap-2">
                <Button type="submit">Simpan</Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
                  Batal
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : items.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Belum ada ingatan. Coba bilang di chat: &quot;ingat ya, namaku ...&quot;
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((m) => (
            <Card key={m.id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <Brain className="h-5 w-5 text-primary" />
                  <div className="flex gap-1">
                    {scopeLabel(m.scope) && (
                      <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">
                        {scopeLabel(m.scope)}
                      </Badge>
                    )}
                    <Badge className="border-primary/30 bg-primary/10 text-primary">
                      {KEY_LABELS[m.key] ?? m.key}
                    </Badge>
                  </div>
                </div>
                <CardTitle className="pt-2 text-base">{m.value}</CardTitle>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <p className="text-[11px] text-muted-foreground">
                  {m.source === "extracted" ? "Otomatis dari chat" : "Kamu yang minta"} ·{" "}
                  {formatDateTime(m.updated_at)}
                </p>
                <Button size="sm" variant="ghost" onClick={() => remove(m.id)}>
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
