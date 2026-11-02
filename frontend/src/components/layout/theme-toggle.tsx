"use client";

import { useTheme } from "@/components/providers/theme-provider";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 cursor-pointer"
      title={theme === "light" ? "Switch to Dark Theme" : "Switch to Light Theme"}
      aria-label="Toggle theme"
    >
      {theme === "light" ? (
        <Moon className="h-4 w-4 text-slate-700 hover:text-indigo-600 transition-transform" />
      ) : (
        <Sun className="h-4 w-4 text-amber-400 hover:text-amber-300 transition-transform" />
      )}
    </button>
  );
}
