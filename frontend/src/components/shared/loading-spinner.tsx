import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  label?: string;
  className?: string;
}

export function LoadingSpinner({
  size = "md",
  label,
  className,
}: LoadingSpinnerProps) {
  const sizeMap = {
    sm: "h-4 w-4",
    md: "h-6 w-6",
    lg: "h-8 w-8",
  };

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center p-6 text-slate-500 dark:text-slate-400",
        className
      )}
    >
      <Loader2 className={cn("animate-spin text-indigo-600", sizeMap[size])} />
      {label && <p className="mt-2 text-xs font-medium">{label}</p>}
    </div>
  );
}
