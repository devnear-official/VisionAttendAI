"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Download, TrendingUp, AlertCircle, RefreshCw, BarChart2, ShieldCheck, Users } from "lucide-react";
import { apiClient } from "@/lib/api-client";

interface DepartmentStat {
  department: string;
  total_students: number;
  present_today: number;
  attendance_rate: number;
}

interface DailyTrendStat {
  date: string;
  attendance_count: number;
  unique_students: number;
}

interface ReportsResponse {
  monthly_attendance_rate: number;
  total_monthly_checkins: number;
  mean_confidence: number;
  total_active_students: number;
  registered_face_templates: number;
  departments: DepartmentStat[];
  daily_trends: DailyTrendStat[];
}

export default function ReportsPage() {
  const [isExporting, setIsExporting] = useState(false);

  const {
    data: reports,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<ReportsResponse>({
    queryKey: ["reports-summary"],
    queryFn: () => apiClient.get<ReportsResponse>("/v1/analytics/reports"),
    staleTime: 30000,
  });

  const handleDownloadReport = async () => {
    try {
      setIsExporting(true);
      await apiClient.download(
        "/v1/attendance/export",
        `institutional_attendance_report_${new Date().toISOString().slice(0, 10)}.csv`
      );
    } catch (err) {
      alert(`Report download failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports & Analytics"
        description="Comprehensive attendance trends, department-wise breakdowns, and audit statistics."
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={handleDownloadReport}
              disabled={isExporting}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
            >
              {isExporting ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {isExporting ? "Generating Report..." : "Download CSV Report"}
            </Button>
          </div>
        }
      />

      {/* Error State */}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to aggregate reports from backend: {error instanceof Error ? error.message : "Service error"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetch()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Overview Analytics Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {isLoading ? (
          <>
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
          </>
        ) : (
          <>
            <Card>
              <CardContent className="p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Monthly Attendance Turnout
                </div>
                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-slate-100">
                  {reports ? `${reports.monthly_attendance_rate.toFixed(1)}%` : "0.0%"}
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-emerald-600 font-medium">
                  <TrendingUp className="h-3.5 w-3.5" />
                  <span>
                    {reports?.total_active_students ?? 0} active students enrolled
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Total Validated Check-Ins (30d)
                </div>
                <div className="mt-2 text-3xl font-bold text-slate-900 dark:text-slate-100">
                  {reports?.total_monthly_checkins.toLocaleString() ?? 0}
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Zero duplicate entries logged</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Mean Recognition Quality
                </div>
                <div className="mt-2 text-3xl font-bold text-indigo-600 dark:text-indigo-400">
                  {reports?.mean_confidence ? `${(reports.mean_confidence * 100).toFixed(1)}%` : "N/A"}
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                  <Users className="h-3.5 w-3.5 text-indigo-500" />
                  <span>
                    {reports?.registered_face_templates ?? 0} ArcFace embeddings stored
                  </span>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Department Breakdown Table */}
      <Card>
        <CardHeader>
          <CardTitle>Department-Wise Performance Ledger</CardTitle>
          <CardDescription>
            30-day attendance turnout and engagement ratios categorized by academic departments.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !reports || reports.departments.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500 dark:text-slate-400">
              No department attendance statistics available yet.
            </div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {reports.departments.map((dept, i) => (
                <div key={i} className="flex flex-col sm:flex-row sm:items-center justify-between py-3.5 gap-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {dept.department}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {dept.present_today} verified attendees out of {dept.total_students} enrolled students
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-32 bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-indigo-600 h-full rounded-full"
                        style={{ width: `${Math.min(100, dept.attendance_rate)}%` }}
                      />
                    </div>
                    <Badge variant="outline" className="font-semibold text-xs min-w-16 text-center justify-center">
                      {dept.attendance_rate.toFixed(1)}%
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Daily Attendance Trend */}
      {reports?.daily_trends && reports.daily_trends.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-indigo-600" />
              <CardTitle>Daily Attendance Turnout Trend</CardTitle>
            </div>
            <CardDescription>
              Check-in volume distribution for recent attendance cycles.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Total Check-Ins</th>
                    <th className="px-4 py-3">Unique Students Verified</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                  {reports.daily_trends.map((trend) => (
                    <tr key={trend.date} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <td className="px-4 py-3 font-mono text-slate-800 dark:text-slate-200">
                        {trend.date}
                      </td>
                      <td className="px-4 py-3 font-semibold text-indigo-600 dark:text-indigo-400">
                        {trend.attendance_count}
                      </td>
                      <td className="px-4 py-3 text-emerald-600 dark:text-emerald-400 font-medium">
                        {trend.unique_students}
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