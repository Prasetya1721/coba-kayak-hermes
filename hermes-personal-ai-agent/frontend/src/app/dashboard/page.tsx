"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, ShieldAlert, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import { useAuth } from "@/context/AuthContext";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const WELCOME: ChatMessage = {
  role: "assistant",
  content:
    "Hai! Stella di sini 😊 ada yang bisa dibantu?",
};

export default function ChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const tpl = sessionStorage.getItem("hermes.template");
    if (tpl) {
      setInput(tpl);
      sessionStorage.removeItem("hermes.template");
    }
    const sid = sessionStorage.getItem("hermes.session_id");
    if (sid) {
      setSessionId(sid);
      setMessages([WELCOME]);
      void (async () => {
        try {
          const history = await api.getHistory(sid);
          if (history.length > 0) {
            setMessages([
              WELCOME,
              ...history.map((m) => ({ role: m.role, content: m.content })),
            ]);
          }
        } catch {
          // biarkan chat mulai dari sesi baru bila riwayat gagal dimuat
        }
      })();
      sessionStorage.removeItem("hermes.session_id");
    }
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setNotice(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await api.sendMessage({
        message: text,
        session_id: sessionId ?? undefined,
      });
      setSessionId(res.session_id);
      if (res.scrubbed && res.detections.length > 0) {
        setNotice(
          `Data sensitif terdeteksi dan disensor: ${res.detections.join(", ")}.`,
        );
      }
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Gagal menghubungi asisten. Pastikan backend berjalan.";
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, sessionId]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col md:h-screen">
      <header className="flex items-center justify-between border-b bg-card px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">Chat dengan Hermes</h1>
          <p className="text-xs text-muted-foreground">
            Anda berinteraksi dengan AI. Data sensitif disensor otomatis.
          </p>
        </div>
        <Badge className="border-primary/30 bg-primary/10 text-primary">
          {user?.username}
        </Badge>
      </header>

      <div ref={scrollRef} className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-6 py-6">
        {messages.map((m, i) => (
          <div
            key={i}
            className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}
          >
            {m.role === "assistant" && (
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                <Bot className="h-4 w-4" />
              </span>
            )}
            <Card
              className={cn(
                "max-w-[80%] whitespace-pre-wrap px-4 py-2.5 text-sm leading-relaxed",
                m.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-card",
              )}
            >
              {m.content}
            </Card>
            {m.role === "user" && (
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-secondary">
                <User className="h-4 w-4" />
              </span>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Hermes sedang berpikir…
          </div>
        )}
      </div>

      {notice && (
        <div className="mx-6 mb-2 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <ShieldAlert className="h-4 w-4" /> {notice}
        </div>
      )}

      <div className="border-t bg-card px-6 py-4">
        <div className="flex items-end gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Tulis pesan… (Enter kirim, Shift+Enter baris baru)"
            className="max-h-40 min-h-[44px] resize-none"
          />
          <Button size="icon" onClick={send} disabled={loading || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
