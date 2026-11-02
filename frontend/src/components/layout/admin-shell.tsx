"use client";

import { ReactNode, useState } from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { cn } from "@/lib/utils";

export function AdminShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50">
      {/* Sidebar Navigation */}
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* Main Content Area */}
      <div
        className={cn(
          "flex flex-col min-h-screen transition-all duration-300 ease-in-out",
          collapsed ? "md:pl-16" : "md:pl-64"
        )}
      >
        <Topbar onMobileOpen={() => setMobileOpen(true)} />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>

        <footer className="border-t border-slate-200 bg-white px-6 py-4 text-center text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          VisionAttend-AI &copy; 2026 &bull; Biometric Edge Attendance Infrastructure &bull; Stage 6.1
        </footer>
      </div>
    </div>
  );
}
