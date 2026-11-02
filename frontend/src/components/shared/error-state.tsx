import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Failed to load data",
  message = "An unexpected error occurred while communicating with the server.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-rose-200 bg-rose-50/40 p-8 text-center dark:border-rose-900/50 dark:bg-rose-950/20">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-900/40 dark:text-rose-400">
        <AlertTriangle className="h-6 w-6" />
      </div>
      <h3 className="text-base font-semibold text-rose-900 dark:text-rose-200">
        {title}
      </h3>
      <p className="mt-1 max-w-sm text-sm text-rose-700/80 dark:text-rose-400">
        {message}
      </p>
      {onRetry && (
        <Button
          onClick={onRetry}
          variant="outline"
          size="sm"
          className="mt-4 border-rose-300 text-rose-800 hover:bg-rose-100 dark:border-rose-800 dark:text-rose-300"
        >
          <RefreshCw className="mr-2 h-3.5 w-3.5" />
          Try Again
        </Button>
      )}
    </div>
  );
}
