import { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: ReactNode;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  className?: string;
}

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  className,
}: StatCardProps) {
  return (
    <Card className={cn("overflow-hidden transition-all hover:border-slate-300 dark:hover:border-slate-700", className)}>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {title}
          </p>
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            {icon}
          </div>
        </div>
        <div className="mt-3">
          <div className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
            {value}
          </div>
          {(description || trend) && (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              {trend && (
                <span
                  className={cn(
                    "font-semibold",
                    trend.isPositive ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                  )}
                >
                  {trend.value}
                </span>
              )}
              {description && <span>{description}</span>}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
