import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merges Tailwind class names safely avoiding conflicting classes.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format date to human-readable string.
 */
export function formatDate(dateString: string | Date | null | undefined): string {
  if (!dateString) return "N/A";
  const date = typeof dateString === "string" ? new Date(dateString) : dateString;
  if (isNaN(date.getTime())) return "Invalid Date";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

/**
 * Format datetime to human-readable string with 12h time.
 */
export function formatDateTime(dateString: string | Date | null | undefined): string {
  if (!dateString) return "N/A";
  const date = typeof dateString === "string" ? new Date(dateString) : dateString;
  if (isNaN(date.getTime())) return "Invalid Date";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }).format(date);
}

/**
 * Format similarity score (e.g. 0.8423 -> "84.2%").
 */
export function formatConfidence(score: number | null | undefined): string {
  if (score === null || score === undefined) return "N/A";
  return `${(score * 100).toFixed(1)}%`;
}
