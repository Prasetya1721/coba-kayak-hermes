"use client";

import { useEffect, useState } from "react";
import { Cpu, Loader2, RefreshCw, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api/client";
import type { ModelListResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function ModelsPage() {
  const [data, setData] = useState<ModelListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    try {
      setData(await api.listModels());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat daftar model.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function switchTo(model: string) {
    setBusy(model);
    setError(null);
    setNotice(null);
    try {
      setData(await api.switchModel(model));
      setNotice(`Model aktif diganti ke ${model}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal ganti model.");
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    setBusy("__reset__");
    setError(null);
    try {
      setData(await api.resetModels());
      setNotice("Cooldown dibersihkan, kembali ke model default.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal reset.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Model AI</h1>
          <p className="text-xs text-muted-foreground">
            Kalau satu model kena limit, Stella otomatis pindah ke model berikutnya.
            Kamu juga bisa pilih model manual di sini.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className="h-4 w-4" /> Muat ulang
          </Button>
          <Button variant="ghost" onClick={reset} disabled={busy === "__reset__"}>
            {busy === "__reset__" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            Reset
          </Button>
        </div>
      </div>

      {notice && (
        <p className="mb-4 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600">
          {notice}
        </p>
      )}
      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {loading ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : !data || data.models.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Belum ada model dikonfigurasi. Set OPENAI_MODEL & LLM_MODEL_FALLBACKS di .env.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.models.map((m) => {
            const cooling = m.cooldown_seconds > 0;
            return (
              <Card
                key={m.model}
                className={cn(
                  m.active && "border-primary/60",
                  cooling && "border-amber-500/40",
                )}
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <Cpu className={cn("h-5 w-5", m.active ? "text-primary" : "text-muted-foreground")} />
                    <div className="flex gap-1">
                      {m.active && (
                        <Badge className="border-primary/30 bg-primary/10 text-primary">
                          Aktif
                        </Badge>
                      )}
                      {cooling && (
                        <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-600">
                          Cooldown {m.cooldown_seconds}s
                        </Badge>
                      )}
                    </div>
                  </div>
                  <CardTitle className="pt-2 text-base font-mono">{m.model}</CardTitle>
                  <CardDescription>
                    {m.active
                      ? "Sedang dipakai untuk menjawab."
                      : cooling
                        ? "Dilewati sementara (kena limit/error)."
                        : "Siap jadi cadangan saat model aktif bermasalah."}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button
                    className="w-full"
                    variant={m.active ? "outline" : "default"}
                    disabled={m.active || busy === m.model}
                    onClick={() => switchTo(m.model)}
                  >
                    {busy === m.model && <Loader2 className="h-4 w-4 animate-spin" />}
                    {m.active ? "Sedang aktif" : "Pakai model ini"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <p className="mt-6 text-xs text-muted-foreground">
        Sumber: <span className="font-mono">{data?.provider ?? "-"}</span>. Urutan
        fallback diatur lewat <span className="font-mono">LLM_MODEL_FALLBACKS</span> di
        <span className="font-mono"> .env</span>.
      </p>
    </div>
  );
}
