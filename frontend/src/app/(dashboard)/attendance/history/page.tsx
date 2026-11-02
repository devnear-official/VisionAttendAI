"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Download,
  Search,
  Filter,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Trash2,
  Radio,
} from "lucide-react";
import { apiClient, ApiError } from "@/lib/api-client";
import { useAttendanceRealtime } from "@/lib/hooks/use-attendance-realtime";

interface AttendanceRecord {
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
  created_at: string;
}

interface AttendanceListResponse {
  total: number;
  records: AttendanceRecord[];
}

interface DeviceItem {
  id: string;
  device_code: string;
  device_name: string;
}

export default function AttendanceHistoryPage() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("ALL");
  const [deviceFilter, setDeviceFilter] = useState("ALL");
  const [page, setPage] = useState(1);
  const [isExporting, setIsExporting] = useState(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const pageSize = 25;

  // Real-time WebSocket synchronization (Auto-updates without page reload and without aggressive polling)
  const { isConnected } = useAttendanceRealtime();

  const handleSearchChange = (val: string) => {
    setSearchTerm(val);
    setPage(1);
    setDebouncedSearch(val);
  };

  // Load devices for device filter dropdown
  const { data: devicesData } = useQuery<{ total: number; devices: DeviceItem[] }>({
    queryKey: ["devices-list"],
    queryFn: () => apiClient.get<{ total: number; devices: DeviceItem[] }>("/v1/devices?limit=100"),
    staleTime: 60000,
  });

  // Query historical attendance records
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<AttendanceListResponse>({
    queryKey: [
      "attendance-history",
      {
        page,
        search: debouncedSearch,
        startDate,
        endDate,
        department: departmentFilter,
        device: deviceFilter,
      },
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("skip", ((page - 1) * pageSize).toString());
      params.set("limit", pageSize.toString());
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (departmentFilter !== "ALL") params.set("department", departmentFilter);
      if (deviceFilter !== "ALL") params.set("device_id", deviceFilter);

      return apiClient.get<AttendanceListResponse>(`/v1/attendance?${params.toString()}`);
    },
    staleTime: 60000, // Kept long because WebSocket provides instant event-driven invalidation
  });

  // Delete attendance record mutation
  const deleteMutation = useMutation({
    mutationFn: async (recordId: string) => {
      return apiClient.delete<{ status: string; message: string }>(`/v1/attendance/${recordId}`);
    },
    onSuccess: (res) => {
      setActionNotice(res.message);
      queryClient.invalidateQueries({ queryKey: ["attendance-history"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["live-attendance"] });
      queryClient.invalidateQueries({ queryKey: ["students"] });
      setTimeout(() => setActionNotice(null), 6000);
    },
    onError: (err: ApiError) => {
      alert(`Delete failed: ${err.message}`);
    },
  });

  const handleDeleteRecord = (r: AttendanceRecord) => {
    const confirmed = confirm(
      `Delete check-in record for "${r.student_name_snapshot}" (${r.student_id_snapshot}) on ${r.attendance_date}?\n\nOnce deleted, this student will be able to take attendance again when they stand in front of the camera.`
    );
    if (confirmed) {
      deleteMutation.mutate(r.id);
    }
  };

  const handleExportCSV = async () => {
    try {
      setIsExporting(true);
      const params = new URLSearchParams();
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (departmentFilter !== "ALL") params.set("department", departmentFilter);
      if (deviceFilter !== "ALL") params.set("device_id", deviceFilter);

      await apiClient.download(
        `/v1/attendance/export?${params.toString()}`,
        `attendance_audit_${new Date().toISOString().slice(0, 10)}.csv`
      );
    } catch (err) {
      alert(`Export failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleResetFilters = () => {
    setSearchTerm("");
    setDebouncedSearch("");
    setStartDate("");
    setEndDate("");
    setDepartmentFilter("ALL");
    setDeviceFilter("ALL");
    setPage(1);
  };

  const formatDate = (isoDate: string) => {
    try {
      return new Date(isoDate).toLocaleDateString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoDate;
    }
  };

  const formatTime = (isoString: string) => {
    try {
      return new Date(isoString).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  const departmentsList = [
    "ALL",
    "Computer Science & Engineering",
    "Electrical & Electronic Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Business Administration",
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance Ledger"
        description="Immutable check-in audit records preserving point-in-time student identity snapshots."
        actions={
          <div className="flex items-center gap-2">
            <Badge
              variant={isConnected ? "success" : "secondary"}
              className="gap-1.5 py-1 px-2.5 text-xs font-normal"
            >
              <span className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500 animate-pulse" : "bg-slate-400"}`} />
              <span>{isConnected ? "Live Auto-Sync Active" : "Connecting..."}</span>
            </Badge>

            <Button
              size="sm"
              variant="outline"
              onClick={handleExportCSV}
              disabled={isExporting}
              className="gap-1.5 text-slate-700 dark:text-slate-200"
            >
              {isExporting ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {isExporting ? "Exporting..." : "Export CSV"}
            </Button>
          </div>
        }
      />

      {/* Action Notification Banner */}
      {actionNotice && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600" />
            <span>{actionNotice}</span>
          </div>
          <button
            onClick={() => setActionNotice(null)}
            className="text-emerald-700 hover:text-emerald-900 dark:text-emerald-300 font-semibold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
          {/* Search by student ID or name */}
          <div className="relative md:col-span-2">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Search by student ID or name..."
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-9 text-xs"
            />
          </div>

          {/* Department Filter */}
          <div>
            <select
              value={departmentFilter}
              onChange={(e) => {
                setDepartmentFilter(e.target.value);
                setPage(1);
              }}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
            >
              {departmentsList.map((d) => (
                <option key={d} value={d}>
                  {d === "ALL" ? "All Departments" : d}
                </option>
              ))}
            </select>
          </div>

          {/* Device Filter */}
          <div>
            <select
              value={deviceFilter}
              onChange={(e) => {
                setDeviceFilter(e.target.value);
                setPage(1);
              }}
              className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
            >
              <option value="ALL">All Edge Devices</option>
              {devicesData?.devices.map((dev) => (
                <option key={dev.id} value={dev.id}>
                  {dev.device_name} ({dev.device_code})
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters button */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleResetFilters}
              className="w-full gap-1 text-xs text-slate-600 dark:text-slate-300"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset Filters
            </Button>
          </div>
        </div>

        {/* Date Range Row */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div className="flex items-center gap-1.5 text-slate-500">
            <Filter className="h-3.5 w-3.5 text-slate-400" />
            <span>Date Range:</span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="h-8 w-36 text-xs"
            />
            <span className="text-slate-400">to</span>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="h-8 w-36 text-xs"
            />
          </div>

          <div className="ml-auto flex items-center gap-1.5 text-emerald-600 text-[11px] font-medium">
            <Radio className="h-3.5 w-3.5" />
            <span>Instant event-driven sync &bull; No page reload required</span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to load attendance records: {error instanceof Error ? error.message : "Service error"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetch()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Audit Ledger Table */}
      <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-5 py-3.5">Date</th>
                <th className="px-5 py-3.5">Student ID (Snapshot)</th>
                <th className="px-5 py-3.5">Student Name (Snapshot)</th>
                <th className="px-5 py-3.5">Department</th>
                <th className="px-5 py-3.5">Check-In Time</th>
                <th className="px-5 py-3.5">Device Node</th>
                <th className="px-5 py-3.5">ArcFace Score</th>
                <th className="px-5 py-3.5">Status</th>
                <th className="px-5 py-3.5">Audit Record UUID</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, idx) => (
                  <tr key={idx}>
                    <td colSpan={10} className="px-5 py-3">
                      <Skeleton className="h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : !data || data.records.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-5 py-12 text-center text-slate-500 dark:text-slate-400">
                    <p className="font-semibold text-sm">No attendance records found</p>
                    <p className="text-xs text-slate-400 mt-1">
                      {debouncedSearch || startDate || endDate || departmentFilter !== "ALL" || deviceFilter !== "ALL"
                        ? "Try clearing filters to see all historical check-in audit records."
                        : "Attendance records captured by edge devices will be automatically recorded here."}
                    </p>
                  </td>
                </tr>
              ) : (
                data.records.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <td className="px-5 py-3.5 font-medium text-slate-900 dark:text-slate-100">
                      {formatDate(r.attendance_date)}
                    </td>
                    <td className="px-5 py-3.5 font-mono font-medium text-slate-800 dark:text-slate-200">
                      {r.student_id_snapshot}
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900 dark:text-slate-100">
                      {r.student_name_snapshot}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-300">
                      {r.department || "Unassigned"}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-600 dark:text-slate-300">
                      {formatTime(r.check_in_time)}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-300">
                      {r.device_name || r.device_code || (r.device_id ? `Device ${r.device_id.slice(0, 8)}` : "Direct API")}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge variant="success" className="font-mono text-[11px] font-medium">
                        {r.recognition_confidence !== null
                          ? `${(r.recognition_confidence * 100).toFixed(1)}%`
                          : "100.0%"}
                      </Badge>
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge variant="success" className="text-[10px] uppercase">
                        {r.status}
                      </Badge>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[10px] text-slate-400" title={r.id}>
                      {r.id.slice(0, 8)}...{r.id.slice(-4)}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={deleteMutation.isPending}
                        onClick={() => handleDeleteRecord(r)}
                        className="h-7 px-2.5 text-[11px] text-rose-500 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30 gap-1 font-medium transition-colors"
                        title="Delete check-in so student can re-check in today"
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Toolbar */}
        {data && data.total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900 text-xs">
            <span className="text-slate-500">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, data.total)} of {data.total} records
            </span>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 gap-1"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </Button>
              <span className="px-2 font-medium text-slate-700 dark:text-slate-300">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-8 gap-1"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}