import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatRelative(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  const diff = date.getTime() - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  if (mins < 1) return diff >= 0 ? "sekarang" : "baru saja";
  if (mins < 60) return diff >= 0 ? `dalam ${mins} menit` : `${mins} menit lalu`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return diff >= 0 ? `dalam ${hours} jam` : `${hours} jam lalu`;
  const days = Math.round(hours / 24);
  return diff >= 0 ? `dalam ${days} hari` : `${days} hari lalu`;
}
