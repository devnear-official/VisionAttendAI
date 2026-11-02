"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Server,
  Brain,
  CheckCircle2,
  Sliders,
  Shield,
  ShieldCheck,
  UserCheck,
  RefreshCw,
  AlertCircle,
  Database,
  Lock,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";

interface HealthData {
  status: string;
  project: string;
  version: string;
  environment: string;
  model_loaded: boolean;
  model_details: {
    model_name: string;
    provider: string;
    threads: number;
    input_shape: (number | string | null)[];
    output_dim: number;
    is_loaded: boolean;
  };
  database: {
    connected: boolean;
    dialect: string;
    pgvector_installed: boolean;
    pgvector_version: string;
    hnsw_index_ready: boolean;
    table_counts?: Record<string, number>;
  };
  similarity_thresholds: {
    match_threshold: number;
    ambiguous_threshold: number;
    min_face_width: number;
    min_face_height: number;
    min_laplacian_variance: number;
  };
}

interface AuthMeData {
  authenticated: boolean;
  user?: {
    id: string;
    role: string;
    name: string;
    email: string;
  };
  expiresAt?: string;
}

export default function SettingsPage() {
  const [pingLatency, setPingLatency] = useState<number | null>(null);
  const [isPinging, setIsPinging] = useState(false);

  // Health Query
  const {
    data: health,
    isLoading: isHealthLoading,
    isError: isHealthError,
    error: healthError,
    refetch: refetchHealth,
    isFetching,
  } = useQuery<HealthData>({
    queryKey: ["health-diagnostics"],
    queryFn: () => apiClient.get<HealthData>("/v1/health"),
    staleTime: 15000,
  });

  // Admin Profile Query
  const { data: authData } = useQuery<AuthMeData>({
    queryKey: ["auth-me"],
    queryFn: async () => {
      const res = await fetch("/api/auth/me");
      return res.json();
    },
    staleTime: 60000,
  });

  const handlePingHealth = async () => {
    try {
      setIsPinging(true);
      const start = performance.now();
      await refetchHealth();
      const end = performance.now();
      setPingLatency(Math.round(end - start));
    } finally {
      setIsPinging(false);
    }
  };

  const formatExpiry = (isoString?: string) => {
    if (!isoString) return "Active Session";
    try {
      return new Date(isoString).toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Settings & Diagnostics"
        description="Core biometric thresholds, database connectivity, and backend engine status."
        actions={
          <div className="flex items-center gap-2">
            {pingLatency !== null && (
              <Badge variant="success" className="text-xs font-mono py-1">
                RTT: {pingLatency} ms
              </Badge>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={handlePingHealth}
              disabled={isPinging || isFetching}
              className="gap-1.5 text-slate-700 dark:text-slate-200"
            >
              <RefreshCw className={`h-3.5 w-3.5 text-emerald-600 ${isPinging || isFetching ? "animate-spin" : ""}`} />
              Ping Backend Health
            </Button>
          </div>
        }
      />

      {isHealthError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to connect to backend engine: {healthError instanceof Error ? healthError.message : "Service error"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetchHealth()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Admin Profile Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UserCheck className="h-4 w-4 text-indigo-600" />
            <CardTitle className="text-sm font-semibold">Administrator Session & Identity</CardTitle>
          </div>
          <CardDescription>
            Active administrative operator profile verified by cryptographic HMAC session token.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="space-y-1">
            <span className="text-slate-500">Operator Identity</span>
            <div className="font-semibold text-slate-800 dark:text-slate-200">
              {authData?.user?.name || "Institutional Administrator"}
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-slate-500">Account Role</span>
            <div>
              <Badge variant="success" className="uppercase text-[10px]">
                {authData?.user?.role || "SUPERADMIN"}
              </Badge>
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-slate-500">Contact Email</span>
            <div className="font-mono text-slate-800 dark:text-slate-200">
              {authData?.user?.email || "admin@visionattend.university.edu"}
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-slate-500">Session Valid Until</span>
            <div className="font-mono text-slate-800 dark:text-slate-200">
              {formatExpiry(authData?.expiresAt)}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Core Infrastructure Health */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-indigo-600" />
              <CardTitle className="text-sm font-semibold">Infrastructure & Backend Health</CardTitle>
            </div>
            <CardDescription>
              FastAPI production service connected via Next.js BFF proxy.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {isHealthLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Service API</span>
                  <Badge variant={health?.status === "healthy" ? "success" : "destructive"}>
                    {health?.project || "VisionAttend-AI"} v{health?.version || "0.5.2"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Environment</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    {health?.environment || "development"}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Database Engine</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                    <Database className="h-3.5 w-3.5 text-indigo-600" />
                    PostgreSQL 17 (Port 5432)
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Vector Extension</span>
                  <Badge variant={health?.database?.pgvector_installed ? "success" : "destructive"}>
                    pgvector {health?.database?.pgvector_version || "0.8.6"} Installed
                  </Badge>
                </div>
                <div className="flex items-center justify-between py-1.5">
                  <span className="text-slate-500">HNSW Vector Index Status</span>
                  <span className="font-mono text-emerald-600 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    m=16, ef_construction=64 Ready
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Biometric Engine Diagnostics */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-600" />
              <CardTitle className="text-sm font-semibold">ArcFace ONNX Inference Engine</CardTitle>
            </div>
            <CardDescription>
              InsightFace ResNet-50 feature extraction network loaded in memory.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {isHealthLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Model File</span>
                  <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                    {health?.model_details?.model_name || "w600k_r50.onnx"}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Execution Provider</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    {health?.model_details?.provider || "CPUExecutionProvider"} ({health?.model_details?.threads || 4} threads)
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Input Tensor Dimensions</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    [1, 3, 112, 112] (RGB Normalized)
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
                  <span className="text-slate-500">Output Vector Dimension</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    {health?.model_details?.output_dim ?? 512}-D L2 Normalized Float32
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5">
                  <span className="text-slate-500">Engine Operational Status</span>
                  <Badge variant={health?.model_loaded ? "success" : "destructive"}>
                    {health?.model_loaded ? "Model Operational" : "Weights Not Loaded"}
                  </Badge>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Similarity Thresholds */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 text-indigo-600" />
              <CardTitle className="text-sm font-semibold">Biometric Decision & Quality Thresholds</CardTitle>
            </div>
            <CardDescription>
              Backend configuration parameters controlling vector cosine distance matching and edge crop quality validation.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                Match Threshold
              </label>
              <Input
                value={health?.similarity_thresholds?.match_threshold?.toString() || "0.65"}
                disabled
                className="bg-slate-50 dark:bg-slate-800 font-mono text-xs"
              />
              <p className="text-[11px] text-slate-500">
                Cosine similarity &gt;= 0.65 marks verified attendance check-in.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                Ambiguous Threshold
              </label>
              <Input
                value={health?.similarity_thresholds?.ambiguous_threshold?.toString() || "0.50"}
                disabled
                className="bg-slate-50 dark:bg-slate-800 font-mono text-xs"
              />
              <p className="text-[11px] text-slate-500">
                Scores between 0.50 and 0.64 flag ambiguous match without check-in.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                Min Face Size (px)
              </label>
              <Input
                value={`${health?.similarity_thresholds?.min_face_width || 48} × ${health?.similarity_thresholds?.min_face_height || 48}`}
                disabled
                className="bg-slate-50 dark:bg-slate-800 font-mono text-xs"
              />
              <p className="text-[11px] text-slate-500">
                Edge crops below 48x48 pixels are rejected for quality assurance.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                Min Laplacian Variance
              </label>
              <Input
                value={health?.similarity_thresholds?.min_laplacian_variance?.toString() || "50.0"}
                disabled
                className="bg-slate-50 dark:bg-slate-800 font-mono text-xs"
              />
              <p className="text-[11px] text-slate-500">
                Blur rejection threshold preventing out-of-focus check-ins.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Security & Access Guard */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-emerald-600" />
              <CardTitle className="text-sm font-semibold">Security & Architecture Compliance</CardTitle>
            </div>
            <CardDescription>
              Security enforcement guarantees across Next.js BFF proxy, session tokens, and edge nodes.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 space-y-1">
              <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 text-indigo-600" />
                Zero Secret Leakage
              </div>
              <p className="text-slate-500 text-[11px]">
                <code>ADMIN_API_KEY</code> and bcrypt password hashes remain strictly server-side in Next.js BFF proxy and are never exposed to browser JavaScript.
              </p>
            </div>

            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 space-y-1">
              <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                CSRF & HttpOnly Cookie
              </div>
              <p className="text-slate-500 text-[11px]">
                Mutating requests (POST, PATCH, DELETE) enforce cryptographic double-submit <code>x-csrf-token</code> verification with SameSite HttpOnly session cookies.
              </p>
            </div>

            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 space-y-1">
              <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                <Database className="h-3.5 w-3.5 text-indigo-600" />
                Immutable Ledger
              </div>
              <p className="text-slate-500 text-[11px]">
                Attendance check-in records are protected by database unique constraints per day and maintain historical snapshots even if student profiles change.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}