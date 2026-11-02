"use client";

import { useState, useEffect } from "react";
import { Menu, Bell, CheckCircle2, AlertCircle } from "lucide-react";
import { Breadcrumbs } from "./breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { ThemeToggle } from "./theme-toggle";

interface TopbarProps {
  onMobileOpen: () => void;
}

export function Topbar({ onMobileOpen }: TopbarProps) {
  const [healthStatus, setHealthStatus] = useState<"healthy" | "degraded" | "checking">("checking");

  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch("/api/proxy/v1/health");
        if (res.ok) {
          const data = await res.json();
          setHealthStatus(data.status === "healthy" ? "healthy" : "degraded");
        } else {
          setHealthStatus("degraded");
        }
      } catch {
        setHealthStatus("degraded");
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-20 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMobileOpen}
          className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50 md:hidden dark:border-slate-700 dark:text-slate-200"
          title="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <Breadcrumbs />
      </div>

      <div className="flex items-center gap-2.5">
        {/* Backend Health Badge */}
        <div className="flex items-center gap-1.5 text-xs">
          {healthStatus === "healthy" && (
            <Badge variant="success" className="gap-1 font-normal">
              <CheckCircle2 className="h-3 w-3 text-emerald-600" />
              <span className="hidden sm:inline">FastAPI :8000 Online</span>
              <span className="sm:hidden">Online</span>
            </Badge>
          )}
          {healthStatus === "degraded" && (
            <Badge variant="destructive" className="gap-1 font-normal">
              <AlertCircle className="h-3 w-3 text-rose-600" />
              <span>Offline</span>
            </Badge>
          )}
          {healthStatus === "checking" && (
            <Badge variant="secondary" className="gap-1 font-normal">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-pulse" />
              <span className="hidden sm:inline">Checking Core...</span>
            </Badge>
          )}
        </div>

        {/* Theme Toggle Button (Light/Dark) */}
        <ThemeToggle />

        {/* Notification Bell */}
        <button
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800"
          title="System notifications"
        >
          <Bell className="h-4 w-4" />
        </button>

        {/* User Avatar */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-200 dark:border-slate-800">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-semibold text-xs dark:bg-indigo-950 dark:text-indigo-300">
            AD
          </div>
          <div className="hidden lg:flex flex-col text-left leading-tight">
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
              Admin
            </span>
            <span className="text-[10px] text-slate-500 dark:text-slate-400">
              Biometrics Superuser
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
