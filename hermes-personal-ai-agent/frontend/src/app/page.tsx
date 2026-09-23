import Link from "next/link";
import {
  Bell,
  Globe,
  Server,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const FEATURES = [
  {
    icon: Sparkles,
    title: "Menjawab pertanyaan",
    body: "Tanya apa saja, kapan saja. Hermes menjawab dengan konteks dan pencarian web real-time.",
  },
  {
    icon: Server,
    title: "Mengelola perangkat",
    body: "Cek status server dan jalankan perintah terbatas via SSH dengan whitelist aman.",
  },
  {
    icon: Globe,
    title: "Mengelola web",
    body: "Deploy ke Vercel, update repository GitHub, dan pantau uptime situs Anda.",
  },
  {
    icon: Bell,
    title: "Mengelola notifikasi",
    body: "Kirim & jadwalkan pengingat otomatis ke Telegram atau WhatsApp.",
  },
  {
    icon: TerminalSquare,
    title: "Vibe coding",
    body: "Dampingi alur kerja coding Anda dengan perintah cepat dan template siap pakai.",
  },
  {
    icon: ShieldCheck,
    title: "Privasi terjaga",
    body: "Penyensoran data sensitif, enkripsi AES-256, dan hak hapus data sesuai UU PDP.",
  },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-background via-background to-accent/40">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2 font-semibold">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary text-primary-foreground">
            H
          </span>
          Hermes
        </div>
        <nav className="flex items-center gap-2">
          <Button variant="ghost" asChild>
            <Link href="/login">Masuk</Link>
          </Button>
          <Button asChild>
            <Link href="/register">Mulai Gratis</Link>
          </Button>
        </nav>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-16 pt-10 text-center animate-fade-in">
        <span className="inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" /> Asisten pribadi AI 24/7
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-6xl">
          Hermes Personal AI Agent
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          Hubungkan Telegram atau WhatsApp, lalu biarkan Hermes mengurus coding,
          website, notifikasi, dan pertanyaan Anda — dengan privasi yang terjaga.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Button size="lg" asChild>
            <Link href="/register">Buat akun sekarang</Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link href="/login">Saya sudah punya akun</Link>
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Onboarding kurang dari 10 menit. Data Anda terenkripsi dan bisa dihapus kapan saja.
        </p>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title} className="animate-slide-up">
              <CardHeader>
                <f.icon className="h-6 w-6 text-primary" />
                <CardTitle className="pt-2">{f.title}</CardTitle>
                <CardDescription>{f.body}</CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Aktif melalui dashboard atau langsung dari chat Anda.
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <footer className="border-t py-8 text-center text-sm text-muted-foreground">
        Hermes Personal AI Agent — self-hosted, single-user, patuh UU PDP.
      </footer>
    </main>
  );
}
