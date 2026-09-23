"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Bell,
  Bot,
  History,
  LayoutDashboard,
  FileCode2,
  Loader2,
  LogOut,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Chat", icon: Bot },
  { href: "/dashboard/history", label: "Riwayat", icon: History },
  { href: "/dashboard/templates", label: "Template", icon: FileCode2 },
  { href: "/dashboard/notifications", label: "Notifikasi", icon: Bell },
  { href: "/dashboard/onboarding", label: "Onboarding", icon: Sparkles },
  { href: "/dashboard/privacy", label: "Privasi", icon: ShieldCheck },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 flex-col border-r bg-card px-3 py-5 md:flex">
        <Link href="/dashboard" className="mb-6 flex items-center gap-2 px-2 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            H
          </span>
          Hermes
        </Link>

        <nav className="flex-1 space-y-1">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 border-t pt-4">
          <div className="px-3 pb-2 text-xs text-muted-foreground">
            Masuk sebagai
            <div className="truncate font-medium text-foreground">{user.username}</div>
          </div>
          <Button variant="ghost" className="w-full justify-start" onClick={logout}>
            <LogOut className="h-4 w-4" /> Keluar
          </Button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center gap-3 border-b bg-card px-4 py-3 md:hidden">
          <LayoutDashboard className="h-5 w-5 text-primary" />
          <span className="font-semibold">Hermes</span>
          <Button variant="ghost" size="icon" className="ml-auto" onClick={logout}>
            <LogOut className="h-4 w-4" />
          </Button>
        </header>
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
