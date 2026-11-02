"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Camera,
  Radio,
  History,
  BarChart3,
  Cpu,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

interface NavItem {
  title: string;
  href: string;
  icon: typeof LayoutDashboard;
  badge?: string;
  live?: boolean;
}

const navItems: NavItem[] = [
  {
    title: "Overview",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    title: "Students",
    href: "/students",
    icon: Users,
  },
  {
    title: "Face Enrollment",
    href: "/enrollment",
    icon: Camera,
  },
  {
    title: "Live Attendance",
    href: "/attendance/live",
    icon: Radio,
    live: true,
  },
  {
    title: "Attendance History",
    href: "/attendance/history",
    icon: History,
  },
  {
    title: "Reports & Analytics",
    href: "/reports",
    icon: BarChart3,
  },
  {
    title: "Edge Devices",
    href: "/devices",
    icon: Cpu,
  },
  {
    title: "System Settings",
    href: "/settings",
    icon: Settings,
  },
];

export function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onMobileClose,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  const sidebarContent = (
    <div className="flex h-full flex-col justify-between bg-slate-900 text-slate-100 border-r border-slate-800">
      {/* Brand Header */}
      <div>
        <div className="flex h-16 items-center justify-between px-4 border-b border-slate-800/80">
          <Link
            href="/dashboard"
            className="flex items-center gap-2.5 overflow-hidden"
            onClick={onMobileClose}
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/30">
              <ShieldCheck className="h-5 w-5" />
            </div>
            {!collapsed && (
              <div className="flex flex-col leading-tight">
                <span className="font-bold tracking-tight text-white text-base">
                  VisionAttend<span className="text-indigo-400">.AI</span>
                </span>
                <span className="text-[10px] text-slate-400 uppercase tracking-widest font-medium">
                  Biometric SaaS
                </span>
              </div>
            )}
          </Link>
          <button
            onClick={onToggle}
            className="hidden md:flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="space-y-1 p-2.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onMobileClose}
                className={cn(
                  "group relative flex items-center rounded-md px-3 py-2.5 text-xs font-medium transition-all",
                  isActive
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-300 hover:bg-slate-800/70 hover:text-white"
                )}
                title={collapsed ? item.title : undefined}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform group-hover:scale-105",
                    isActive ? "text-white" : "text-slate-400 group-hover:text-slate-200",
                    !collapsed && "mr-3"
                  )}
                />
                {!collapsed && (
                  <span className="truncate flex-1">{item.title}</span>
                )}
                {!collapsed && item.live && (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer / Account / Logout */}
      <div className="p-3 border-t border-slate-800/80">
        {!collapsed ? (
          <div className="flex items-center justify-between rounded-md bg-slate-800/40 p-2.5">
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-white truncate">
                Admin Console
              </span>
              <span className="text-[10px] text-emerald-400 font-medium">
                ● Master Token Verified
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-rose-400 transition-colors p-1"
              title="Sign Out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex justify-center">
            <button
              onClick={handleLogout}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
              title="Sign Out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={cn(
          "hidden md:block fixed inset-y-0 left-0 z-30 transition-all duration-300 ease-in-out",
          collapsed ? "w-16" : "w-64"
        )}
      >
        {sidebarContent}
      </aside>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm md:hidden"
          onClick={onMobileClose}
        />
      )}

      {/* Mobile Drawer */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 transition-transform duration-300 ease-in-out md:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
