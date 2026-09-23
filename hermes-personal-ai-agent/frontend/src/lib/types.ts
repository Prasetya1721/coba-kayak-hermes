export type ChatRole = "user" | "assistant";

export interface User {
  id: string;
  username: string;
  email: string;
  consent_given: boolean;
  created_at: string;
}

export interface Profile {
  user_id: string;
  display_name: string | null;
  phone_number: string | null;
  timezone: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  timestamp?: string | null;
}

export interface ChatSession {
  id: string;
  platform: string;
  platform_chat_id: string;
  created_at: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  scrubbed: boolean;
  detections: string[];
}

export interface Template {
  id: string;
  title: string;
  description: string | null;
  command_pattern: string;
  category: string | null;
  is_builtin: boolean;
  created_at: string;
}

export interface Notification {
  id: string;
  message: string;
  schedule_cron: string | null;
  run_at: string | null;
  platform: "telegram" | "whatsapp";
  target_chat_id: string | null;
  next_run: string | null;
  active: boolean;
  created_at: string;
}

export interface OnboardingStatus {
  completed: boolean;
  steps: Record<string, boolean>;
  next_step: string | null;
}

export interface Credential {
  id: string;
  service_name: string;
  created_at: string;
}
