"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck, KeyRound, Eye, EyeOff, Loader2, Lock, AlertCircle, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { loginSchema, LoginFormData } from "@/lib/validators/auth.schema";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isExpired = searchParams.get("expired") === "1";
  const redirectTarget = searchParams.get("from") || "/dashboard";

  const [showKey, setShowKey] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      apiKey: "",
    },
  });

  async function onSubmit(data: LoginFormData) {
    setServerError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: data.apiKey.trim() }),
      });

      const resData = await res.json();

      if (!res.ok) {
        throw new Error(resData.error || "Authentication failed. Invalid Admin Master Key.");
      }

      router.push(redirectTarget);
      router.refresh();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Authentication error connecting to server.");
    }
  }

  return (
    <Card className="border-slate-800 bg-slate-950/80 shadow-2xl backdrop-blur-md">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-lg text-white">Administrator Access</CardTitle>
        <CardDescription className="text-slate-400 text-xs">
          Enter your institutional master token to access biometric attendance controls.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isExpired && (
          <div className="mb-4 flex items-center gap-2 rounded-md border border-amber-800/60 bg-amber-950/40 p-3 text-xs text-amber-300">
            <Clock className="h-4 w-4 shrink-0" />
            <span>Your previous administrative session has expired. Please sign in again.</span>
          </div>
        )}

        {serverError && (
          <div className="mb-4 flex items-center gap-2 rounded-md border border-rose-800/60 bg-rose-950/40 p-3 text-xs text-rose-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{serverError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Master Admin API Key
            </label>
            <div className="relative">
              <KeyRound className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type={showKey ? "text" : "password"}
                placeholder="Enter ADMIN_API_KEY..."
                className="pl-9 pr-10 border-slate-700 bg-slate-900 text-slate-100 placeholder:text-slate-500 focus-visible:ring-indigo-500"
                autoFocus
                {...register("apiKey")}
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-2.5 text-slate-500 hover:text-slate-300"
                tabIndex={-1}
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {errors.apiKey && (
              <p className="text-[11px] text-rose-400 font-medium">
                {errors.apiKey.message}
              </p>
            )}
          </div>

          <Button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Verifying Credentials...
              </>
            ) : (
              <>
                <Lock className="mr-2 h-4 w-4" />
                Sign In to Console
              </>
            )}
          </Button>
        </form>

        {/* Security Notice */}
        <div className="mt-6 rounded-md border border-slate-800/80 bg-slate-900/60 p-3 text-[11px] text-slate-400">
          <div className="font-semibold text-slate-300 mb-1 flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-indigo-400" />
            Zero-Knowledge Client Architecture
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-slate-400">
            <li>Credentials verified server-side only</li>
            <li>Signed, expiring httpOnly session cookie</li>
            <li>Biometric feature vectors stored without raw image files</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 p-4 font-sans text-slate-100">
      <div className="w-full max-w-md">
        {/* Brand Icon & Heading */}
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-xl shadow-indigo-600/30">
            <ShieldCheck className="h-8 w-8" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            VisionAttend<span className="text-indigo-400">.AI</span>
          </h1>
          <p className="mt-1 text-xs text-slate-400 uppercase tracking-widest font-medium">
            University Biometrics Administration
          </p>
        </div>

        <Suspense fallback={
          <div className="flex justify-center p-8 text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
          </div>
        }>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
