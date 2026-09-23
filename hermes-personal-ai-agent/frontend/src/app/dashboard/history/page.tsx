"use client";

import { useEffect, useState } from "react";
import { Bot, History as HistoryIcon, Loader2, Trash2, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api/client";
import type { ChatMessage, ChatSession } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

export default function HistoryPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const rows = await api.listSessions();
      setSessions(rows);
      if (rows.length > 0 && !activeId) {
        await openSession(rows[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat riwayat.");
    } finally {
      setLoading(false);
    }
  }

  async function openSession(id: string) {
    setActiveId(id);
    setLoadingHistory(true);
    try {
      setMessages(await api.getHistory(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal memuat percakapan.");
    } finally {
      setLoadingHistory(false);
    }
  }

  async function removeSession(id: string) {
    try {
      await api.deleteSession(id);
      setSessions((s) => s.filter((x) => x.id !== id));
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menghapus sesi.");
    }
  }

  async function continueInChat(id: string) {
    sessionStorage.setItem("hermes.session_id", id);
    window.location.href = "/dashboard";
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="grid h-full place-items-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col px-6 py-6 md:flex-row md:gap-6">
      <div className="mb-4 w-full md:mb-0 md:w-72 md:shrink-0">
        <h1 className="mb-1 text-lg font-semibold">Riwayat Chat</h1>
        <p className="mb-4 text-xs text-muted-foreground">
          Semua percakapan Anda, didekripsi aman di sisi server.
        </p>
        {error && (
          <p className="mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="scrollbar-thin max-h-64 space-y-2 overflow-y-auto md:max-h-[calc(100vh-220px)]">
          {sessions.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Belum ada percakapan.
            </p>
          )}
          {sessions.map((s) => (
            <Card
              key={s.id}
              className={cn(
                "cursor-pointer p-3 transition-colors hover:border-primary/40",
                activeId === s.id && "border-primary/60 bg-primary/5",
              )}
              onClick={() => openSession(s.id)}
            >
              <div className="flex items-center justify-between gap-2">
                <Badge className="border-primary/30 bg-primary/10 text-primary">
                  {s.platform}
                </Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    void removeSession(s.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              <p className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                {s.platform_chat_id}
              </p>
              <p className="text-[11px] text-muted-foreground">{formatDateTime(s.created_at)}</p>
            </Card>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <HistoryIcon className="h-4 w-4 text-primary" />
            {activeId ? "Percakapan" : "Pilih sesi di kiri"}
          </p>
          {activeId && (
            <Button size="sm" onClick={() => continueInChat(activeId)}>
              Lanjutkan di Chat
            </Button>
          )}
        </div>
        <div className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {loadingHistory && (
            <div className="grid place-items-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          )}
          {!loadingHistory &&
            messages.map((m, i) => (
              <div
                key={i}
                className={cn("flex gap-2", m.role === "user" ? "justify-end" : "justify-start")}
              >
                {m.role === "assistant" && (
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                    <Bot className="h-3.5 w-3.5" />
                  </span>
                )}
                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
                    m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                  )}
                >
                  {m.content}
                </div>
                {m.role === "user" && (
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-secondary">
                    <User className="h-3.5 w-3.5" />
                  </span>
                )}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
