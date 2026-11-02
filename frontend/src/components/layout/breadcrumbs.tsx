"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

const routeNames: Record<string, string> = {
  dashboard: "Overview",
  students: "Students",
  enrollment: "Face Enrollment",
  attendance: "Attendance",
  live: "Live Feed",
  history: "Audit Ledger",
  reports: "Reports & Analytics",
  devices: "Edge Devices",
  settings: "System Settings",
};

export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) return null;

  return (
    <nav className="flex items-center space-x-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
      <Link
        href="/dashboard"
        className="flex items-center hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
      >
        <Home className="h-3.5 w-3.5" />
      </Link>
      {segments.map((segment, index) => {
        const href = "/" + segments.slice(0, index + 1).join("/");
        const isLast = index === segments.length - 1;
        const displayName = routeNames[segment] || segment;

        return (
          <div key={href} className="flex items-center space-x-1.5">
            <ChevronRight className="h-3 w-3 text-slate-400" />
            {isLast ? (
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {displayName}
              </span>
            ) : (
              <Link
                href={href}
                className="hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
              >
                {displayName}
              </Link>
            )}
          </div>
        );
      })}
    </nav>
  );
}
