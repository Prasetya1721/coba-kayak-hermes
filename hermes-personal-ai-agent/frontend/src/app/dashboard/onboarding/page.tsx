"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  Bell,
  CheckCircle2,
  Circle,
  KeyRound,
  Loader2,
  MessageCircle,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import type { OnboardingStatus } from "@/lib/types";

type Step = {
  key: string;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
};

const STEPS: Step[] = [
  {
    key: "account_created",
    title: "Akun dibuat",
    description: "Akun Anda aktif. Lanjut ke langkah berikutnya.",
    icon: CheckCircle2,
  },
  {
    key: "consent_given",
    title: "Persetujuan UU PDP",
    description: "Anda telah menyetujui pemrosesan data percakapan.",
    icon: ShieldCheck,
  },
  {
    key: "llm_configured",
    title: "Atur API key model AI",
    description:
      "Simpan API key OpenAI/Anthropic dari server. Di dashboard ini, hubungi admin untuk set OPENAI_API_KEY.",
    icon: KeyRound,
  },
  {
    key: "telegram_connected",
    title: "Hubungkan Telegram",
    description:
      "Buat bot via @BotFather, lalu daftarkan webhook ke URL backend /api/webhooks/telegram.",
    icon: Send,
  },
  {
    key: "whatsapp_connected",
    title: "Hubungkan WhatsApp",
    description: "Pilih provider: Twilio (resmi) atau Baileys (self-hosted).",
    icon: MessageCircle,
  },
  {
    key: "template_selected",
    title: "Pilih template",
    description: "Gunakan template siap pakai untuk memulai dengan cepat.",
    icon: Sparkles,
  },
  {
    key: "notification_created",
    title: "Buat notifikasi pertama",
    description: "Jadwalkan pengingat ke Telegram/WhatsApp.",
    icon: Bell,
  },
];

const SERVICES = [
  {
    name: "github_token",
    label: "GitHub Token",
    hint: "Personal Access Token (classic), scope 'repo'. Untuk baca repo PMS.",
  },
  {
    name: "ssh_key",
    label: "SSH Password/Key",
    hint: "Password atau private key untuk perangkat/server (dipakai tool execute_ssh).",
  },
  {
    name: "webhook_secret",
    label: "Secret Lainnya",
    hint: "Kredensial umum (nama layanan bisa kamu sesuaikan).",
  },
];

export default function OnboardingPage() {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [credential, setCredential] = useState({ service_name: "github_token", token: "" });
  const [saved, setSaved] = useState(false);
  const [creds, setCreds] = useState<string[]>([]);

  async function load() {
    setLoading(true);
    try {
      setStatus(await api.onboardingStatus());
      const list = await api.listCredentials();
      setCreds(list.map((c) => c.service_name));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat status onboarding.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function saveCredential(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.storeCredential(credential);
      setSaved(true);
      setCredential({ ...credential, token: "" });
      const list = await api.listCredentials();
      setCreds(list.map((c) => c.service_name));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menyimpan kredensial.");
    }
  }

  if (loading) {
    return (
      <div className="grid h-full place-items-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  const completedCount = status
    ? Object.values(status.steps).filter(Boolean).length
    : 0;
  const progress = Math.round((completedCount / STEPS.length) * 100);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold">Onboarding</h1>
        <p className="text-xs text-muted-foreground">
          Ikuti langkah-langkah berikut untuk mengaktifkan asisten Anda ({progress}%).
        </p>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          {STEPS.map((step, index) => {
            const done = status?.steps[step.key] ?? false;
            return (
              <Card key={step.key} className={done ? "border-emerald-500/30" : ""}>
                <CardContent className="flex items-center gap-4 p-4">
                  <span
                    className={
                      done
                        ? "grid h-10 w-10 shrink-0 place-items-center rounded-full bg-emerald-500/10 text-emerald-600"
                        : "grid h-10 w-10 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"
                    }
                  >
                    {done ? <CheckCircle2 className="h-5 w-5" /> : <step.icon className="h-5 w-5" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">
                        {index + 1}. {step.title}
                      </p>
                      {done ? (
                        <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">
                          Selesai
                        </Badge>
                      ) : (
                        <Circle className="h-3 w-3 text-muted-foreground" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{step.description}</p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <KeyRound className="h-4 w-4 text-primary" /> Simpan kredensial layanan
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={saveCredential} className="space-y-3">
                <div className="space-y-2">
                  <Label>Layanan</Label>
                  <select
                    value={credential.service_name}
                    onChange={(e) =>
                      setCredential({ ...credential, service_name: e.target.value })
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  >
                    {SERVICES.map((s) => (
                      <option key={s.name} value={s.name}>
                        {s.label}
                        {creds.includes(s.name) ? " ✓ tersimpan" : ""}
                      </option>
                    ))}
                  </select>
                  <p className="text-[11px] text-muted-foreground">
                    {SERVICES.find((s) => s.name === credential.service_name)?.hint}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Token / secret (disimpan terenkripsi)</Label>
                  <Input
                    type="password"
                    value={credential.token}
                    onChange={(e) => setCredential({ ...credential, token: e.target.value })}
                    placeholder="tempel token di sini"
                    required
                  />
                </div>
                <Button type="submit" className="w-full">
                  Simpan terenkripsi <ArrowRight className="h-4 w-4" />
                </Button>
                {saved && (
                  <p className="text-xs text-emerald-600">
                    Kredensial tersimpan dan dienkripsi. Stella langsung bisa pakai.
                  </p>
                )}
                {creds.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Sudah tersimpan: {creds.join(", ")}
                  </p>
                )}
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tips cepat</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>• Telegram: buat bot, lalu set webhook ke domain HTTPS Anda.</p>
              <p>• WhatsApp resmi: gunakan Twilio sandbox untuk uji coba.</p>
              <p>• Jangan pernah mengirim kata sandi ke chat; Hermes akan menyensornya.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
