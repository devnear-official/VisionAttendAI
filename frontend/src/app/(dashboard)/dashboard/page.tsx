"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, Camera, Radio, CheckCircle2, ArrowUpRight, Cpu, AlertTriangle, RefreshCw, Layers } from "lucide-react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";

interface DepartmentStat {
  department: string;
  total_students: number;
  present_today: number;
  attendance_rate: number;
}

interface AttendanceRecordItem {
  id: string;
  student_id: string | null;
  student_id_snapshot: string;
  student_name_snapshot: string;
  attendance_date: string;
  check_in_time: string;
  device_id: string | null;
  device_name: string | null;
  device_code: string | null;
  department: string | null;
  recognition_confidence: number | null;
  recognition_method: string;
  status: string;
}

interface DashboardSummaryResponse {
  total_students: number;
  total_active_students: number;
  today_attendance_count: number;
  unique_students_present: number;
  attendance_rate: number;
  average_confidence: number | null;
  registered_face_templates: number;
  total_devices: number;
  online_devices: number;
  departments: DepartmentStat[];
  recent_activity: AttendanceRecordItem[];
}

interface HealthResponse {
  status: string;
  project: string;
  version: string;
  environment: string;
  model_loaded: boolean;
  model_details: {
    model_name: string;
    provider?: string;
    output_dim?: number;
  };
  database: {
    connected: boolean;
    pgvector_installed?: boolean;
    pgvector_version?: string;
  };
  similarity_thresholds?: {
    match_threshold?: number;
    ambiguous_threshold?: number;
  };
}

export default function DashboardOverviewPage() {
  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery<DashboardSummaryResponse>({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiClient.get<DashboardSummaryResponse>("/v1/analytics/dashboard"),
    refetchInterval: 10000,
  });

  const { data: health } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => apiClient.get<HealthResponse>("/v1/health"),
    staleTime: 30000,
  });

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Institutional Dashboard"
        description="Real-time biometric attendance metrics and edge camera sensor overview."
        actions={
          <div className="flex items-center gap-2">
            <Link href="/attendance/live">
              <Button size="sm" className="bg-emerald-600 hover:bg-emerald-500 text-white gap-1.5">
                <Radio className="h-3.5 w-3.5" />
                Live Attendance Feed
              </Button>
            </Link>
            <Link href="/enrollment">
              <Button size="sm" variant="outline" className="gap-1.5">
                <Camera className="h-3.5 w-3.5" />
                Enroll Face
              </Button>
            </Link>
          </div>
        }
      />

      {isSummaryError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to synchronize dashboard metrics with backend:{" "}
              {summaryError instanceof Error ? summaryError.message : "Service offline"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetchSummary()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {isSummaryLoading ? (
          <>
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
          </>
        ) : (
          <>
            <StatCard
              title="Total Registered Students"
              value={summary ? summary.total_students.toString() : "0"}
              description={`${summary?.total_active_students ?? 0} active in directory`}
              icon={<Users className="h-4 w-4" />}
              trend={{
                value: `${summary?.registered_face_templates ?? 0} biometrics`,
                isPositive: (summary?.registered_face_templates ?? 0) > 0,
              }}
            />
            <StatCard
              title="Today's Check-Ins"
              value={summary ? summary.today_attendance_count.toString() : "0"}
              description={`${summary?.attendance_rate ?? 0}% daily attendance rate`}
              icon={<CheckCircle2 className="h-4 w-4" />}
              trend={{
                value: `${summary?.unique_students_present ?? 0} unique students`,
                isPositive: (summary?.unique_students_present ?? 0) > 0,
              }}
            />
            <StatCard
              title="Avg ArcFace Confidence"
              value={
                summary?.average_confidence !== null && summary?.average_confidence !== undefined
                  ? `${(summary.average_confidence * 100).toFixed(1)}%`
                  : "N/A"
              }
              description={`Cosine threshold: ${((health?.similarity_thresholds?.match_threshold ?? 0.65) * 100).toFixed(0)}%`}
              icon={<Camera className="h-4 w-4" />}
              trend={{
                value: summary?.average_confidence ? "Optimal" : "Awaiting events",
                isPositive: (summary?.average_confidence ?? 0) >= 0.65,
              }}
            />
            <StatCard
              title="Active Edge Cameras"
              value={summary ? `${summary.online_devices} / ${summary.total_devices}` : "0 / 0"}
              description={`${summary?.online_devices ?? 0} nodes transmitting`}
              icon={<Cpu className="h-4 w-4" />}
              trend={{
                value:
                  summary && summary.total_devices > 0
                    ? `${Math.round((summary.online_devices / summary.total_devices) * 100)}% online`
                    : "0 registered",
                isPositive: (summary?.online_devices ?? 0) > 0,
              }}
            />
          </>
        )}
      </div>

      {/* Grid: Live Activity & System Architecture */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent Attendance Stream */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle>Recent Verified Check-Ins</CardTitle>
              <CardDescription>
                Biometric recognitions captured by classroom entrance cameras today.
              </CardDescription>
            </div>
            <Link href="/attendance/history">
              <Button variant="ghost" size="sm" className="text-xs text-indigo-600 dark:text-indigo-400 gap-1">
                View Ledger
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {isSummaryLoading ? (
              <div className="space-y-3 py-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : !summary?.recent_activity || summary.recent_activity.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500 dark:text-slate-400">
                <p>No verified attendance events recorded yet today.</p>
                <p className="mt-1 text-[11px] text-slate-400">
                  Recognition events from ESP32 edge camera nodes will stream here automatically.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {summary.recent_activity.map((record) => (
                  <div key={record.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 font-semibold text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                        {record.student_name_snapshot.charAt(0)}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                          {record.student_name_snapshot}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          {record.student_id_snapshot}
                          {record.department ? ` • ${record.department}` : ""}
                          {` • ${record.device_name || record.device_code || "Entrance Node"}`}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <Badge variant="success" className="text-[11px] font-medium">
                        {record.recognition_confidence !== null
                          ? `${(record.recognition_confidence * 100).toFixed(1)}% Match`
                          : "Verified"}
                      </Badge>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {formatTime(record.check_in_time)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* System & Model Architecture */}
        <Card>
          <CardHeader>
            <CardTitle>System & Model Architecture</CardTitle>
            <CardDescription>
              Backend microservice status and model specifications.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-xs">
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400">Face Recognition Model</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                {health?.model_details?.model_name || "w600k_r50.onnx"}
              </span>
            </div>
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400">Engine Status</span>
              <Badge variant={health?.model_loaded ? "success" : "destructive"}>
                {health?.model_loaded ? "Operational" : "Model Offline"}
              </Badge>
            </div>
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400">Embedding Vector Size</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                {health?.model_details?.output_dim ?? 512} Dimensions (Normalized)
              </span>
            </div>
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400">Database & Extension</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                PostgreSQL + pgvector {health?.database?.pgvector_version || "0.8.6"}
              </span>
            </div>
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800">
              <span className="text-slate-500 dark:text-slate-400">Cosine Match Threshold</span>
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                {health?.similarity_thresholds?.match_threshold ?? 0.65} (65%)
              </span>
            </div>
            <div className="flex items-center justify-between py-1.5">
              <span className="text-slate-500 dark:text-slate-400">Audit Check-in Policy</span>
              <Badge variant="secondary" className="text-[10px]">1 Check-in / Day</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Department Breakdown */}
      {summary?.departments && summary.departments.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-600" />
              <CardTitle>Department-Wise Attendance Performance</CardTitle>
            </div>
            <CardDescription>
              Aggregated daily turnout categorized by institutional academic departments.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Department</th>
                    <th className="px-4 py-3">Total Active Students</th>
                    <th className="px-4 py-3">Present Today</th>
                    <th className="px-4 py-3">Daily Attendance Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                  {summary.departments.map((dept) => (
                    <tr key={dept.department} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <td className="px-4 py-3 font-semibold text-slate-800 dark:text-slate-200">
                        {dept.department}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300">
                        {dept.total_students}
                      </td>
                      <td className="px-4 py-3 font-medium text-emerald-600 dark:text-emerald-400">
                        {dept.present_today}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-24 bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div
                              className="bg-indigo-600 h-full rounded-full"
                              style={{ width: `${Math.min(100, dept.attendance_rate)}%` }}
                            />
                          </div>
                          <span className="font-semibold text-slate-700 dark:text-slate-300">
                            {dept.attendance_rate.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}