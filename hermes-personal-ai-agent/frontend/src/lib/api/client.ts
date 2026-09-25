/**
 * Typed API client for the Hermes backend.
 *
 * Tokens live in localStorage for this self-hosted single-user app and are
 * attached to every request. On a 401 the client attempts a single refresh,
 * then clears the session.
 */
import type {
  ChatResponse,
  ChatSession,
  Credential,
  MemoryItem,
  Notification,
  OnboardingStatus,
  Profile,
  Template,
  TokenResponse,
  User,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCESS_KEY = "hermes.access";
const REFRESH_KEY = "hermes.refresh";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const tokens = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
  },
  set(t: TokenResponse) {
    localStorage.setItem(ACCESS_KEY, t.access_token);
    localStorage.setItem(REFRESH_KEY, t.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

async function rawRequest<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (tokens.access) headers.set("Authorization", `Bearer ${tokens.access}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (res.status === 401 && retry && tokens.refresh) {
    const refreshed = await tryRefresh();
    if (refreshed) return rawRequest<T>(path, init, false);
    tokens.clear();
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : null) ?? "Terjadi kesalahan.";
    throw new ApiError(detail, res.status);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh }),
    });
    if (!res.ok) return false;
    tokens.set((await res.json()) as TokenResponse);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  // --- auth ---
  register: (body: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
    timezone?: string;
    consent: boolean;
  }) =>
    rawRequest<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  login: async (body: { username: string; password: string }) => {
    const t = await rawRequest<TokenResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
    tokens.set(t);
    return t;
  },

  logout: () => tokens.clear(),

  me: () => rawRequest<User>("/api/auth/me"),

  getProfile: () => rawRequest<Profile>("/api/auth/profile"),

  updateProfile: (body: {
    display_name?: string;
    phone_number?: string;
    timezone?: string;
  }) =>
    rawRequest<Profile>("/api/auth/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // --- chat ---
  sendMessage: (body: { message: string; session_id?: string }) =>
    rawRequest<ChatResponse>("/api/chat/message", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listSessions: () => rawRequest<ChatSession[]>("/api/chat/sessions"),

  getHistory: async (sessionId: string) => {
    const res = await rawRequest<{
      session_id: string;
      messages: { role: "user" | "assistant"; content: string; timestamp: string }[];
    }>(`/api/chat/sessions/${sessionId}`);
    return res.messages;
  },

  deleteSession: (sessionId: string) =>
    rawRequest<void>(`/api/chat/sessions/${sessionId}`, { method: "DELETE" }),

  // --- templates ---
  listTemplates: (category?: string) =>
    rawRequest<Template[]>(
      `/api/templates${category ? `?category=${encodeURIComponent(category)}` : ""}`,
    ),

  createTemplate: (body: {
    title: string;
    description?: string;
    command_pattern: string;
    category?: string;
  }) =>
    rawRequest<Template>("/api/templates", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTemplate: (
    id: string,
    body: Partial<{
      title: string;
      description: string;
      command_pattern: string;
      category: string;
    }>,
  ) =>
    rawRequest<Template>(`/api/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteTemplate: (id: string) =>
    rawRequest<void>(`/api/templates/${id}`, { method: "DELETE" }),

  // --- notifications ---
  listNotifications: (activeOnly = false) =>
    rawRequest<Notification[]>(
      `/api/notifications${activeOnly ? "?active_only=true" : ""}`,
    ),

  createNotification: (body: {
    message: string;
    platform: "telegram" | "whatsapp";
    schedule_cron?: string;
    run_at?: string;
    target_chat_id?: string;
  }) =>
    rawRequest<Notification>("/api/notifications", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  toggleNotification: (id: string) =>
    rawRequest<Notification>(`/api/notifications/${id}/toggle`, { method: "POST" }),

  deleteNotification: (id: string) =>
    rawRequest<void>(`/api/notifications/${id}`, { method: "DELETE" }),

  // --- memories ---
  listMemories: () => rawRequest<MemoryItem[]>("/api/memories"),

  createMemory: (body: { key: string; value: string }) =>
    rawRequest<MemoryItem>("/api/memories", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteMemory: (id: string) =>
    rawRequest<void>(`/api/memories/${id}`, { method: "DELETE" }),

  // --- credentials ---
  listCredentials: () => rawRequest<Credential[]>("/api/credentials"),

  storeCredential: (body: { service_name: string; token: string }) =>
    rawRequest<Credential>("/api/credentials", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteCredential: (serviceName: string) =>
    rawRequest<void>(`/api/credentials/${serviceName}`, { method: "DELETE" }),

  // --- onboarding ---
  onboardingStatus: () => rawRequest<OnboardingStatus>("/api/onboarding/status"),

  // --- privacy ---
  exportData: () => rawRequest<Record<string, unknown>>("/api/privacy/export"),

  deleteAllData: () =>
    rawRequest<{ deleted: boolean; detail: string }>("/api/privacy/data", {
      method: "DELETE",
    }),

  deleteAccount: () => rawRequest<void>("/api/privacy/account", { method: "DELETE" }),
};
