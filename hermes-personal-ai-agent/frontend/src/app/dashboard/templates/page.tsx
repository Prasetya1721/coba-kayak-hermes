"use client";

import { useEffect, useState } from "react";
import { FileCode2, Loader2, Plus, Trash2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Badge } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import type { Template } from "@/lib/types";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState({
    title: "",
    description: "",
    command_pattern: "",
    category: "umum",
  });

  async function load() {
    setLoading(true);
    try {
      setTemplates(await api.listTemplates());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat template.");
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
      await api.createTemplate(draft);
      setDraft({ title: "", description: "", command_pattern: "", category: "umum" });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menyimpan template.");
    }
  }

  async function remove(id: string) {
    await api.deleteTemplate(id);
    await load();
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Template Perintah</h1>
          <p className="text-xs text-muted-foreground">
            Perintah siap pakai untuk memulai cepat. Klik &quot;Gunakan&quot; untuk mengisi chat.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4" /> Template baru
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
            <CardTitle>Buat template</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Judul</Label>
                  <Input
                    value={draft.title}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label>Kategori</Label>
                  <Input
                    value={draft.category}
                    onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Deskripsi</Label>
                <Input
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Pola perintah (gunakan {"{placeholder}"} untuk variabel)</Label>
                <Textarea
                  value={draft.command_pattern}
                  onChange={(e) => setDraft({ ...draft, command_pattern: e.target.value })}
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
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <Card key={t.id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <FileCode2 className="h-5 w-5 text-primary" />
                  {t.is_builtin && (
                    <Badge className="border-primary/30 bg-primary/10 text-primary">
                      Bawaan
                    </Badge>
                  )}
                </div>
                <CardTitle className="pt-2 text-base">{t.title}</CardTitle>
                <CardDescription>{t.description}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto space-y-3">
                <pre className="scrollbar-thin max-h-28 overflow-auto rounded-md bg-muted p-3 text-xs">
                  {t.command_pattern}
                </pre>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={() => {
                      sessionStorage.setItem("hermes.template", t.command_pattern);
                      window.location.href = "/dashboard";
                    }}
                  >
                    <Wand2 className="h-4 w-4" /> Gunakan
                  </Button>
                  {!t.is_builtin && (
                    <Button size="sm" variant="ghost" onClick={() => remove(t.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
