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
  Plus,
  Search,
  Filter,
  Camera,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Edit2,
  X,
  RefreshCw,
  Clock,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api-client";

interface StudentItem {
  id: string;
  student_id: string;
  full_name: string;
  email: string | null;
  department: string | null;
  batch: string | null;
  phone: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  embeddings_count: number;
  attendance_count: number;
  last_attendance_at: string | null;
}

interface StudentListResponse {
  total: number;
  students: StudentItem[];
}

export default function StudentsPage() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState<StudentItem | null>(null);

  // Form states for Create/Edit
  const [formId, setFormId] = useState("");
  const [formName, setFormName] = useState("");
  const [formDept, setFormDept] = useState("Computer Science & Engineering");
  const [formBatch, setFormBatch] = useState("2024");
  const [formEmail, setFormEmail] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formStatus, setFormStatus] = useState("active");
  const [formError, setFormError] = useState<string | null>(null);

  // Debounce search input
  const handleSearchChange = (val: string) => {
    setSearchTerm(val);
    setPage(1);
    setDebouncedSearch(val);
  };

  // TanStack Query to load real students
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<StudentListResponse>({
    queryKey: [
      "students",
      {
        page,
        search: debouncedSearch,
        department: departmentFilter,
        status: statusFilter,
      },
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("skip", ((page - 1) * pageSize).toString());
      params.set("limit", pageSize.toString());
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());
      if (departmentFilter !== "ALL") params.set("department", departmentFilter);
      if (statusFilter !== "ALL") params.set("status_filter", statusFilter);

      return apiClient.get<StudentListResponse>(`/v1/students?${params.toString()}`);
    },
    staleTime: 5000,
  });

  // Create Student Mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      return apiClient.post<StudentItem>("/v1/students", {
        student_id: formId.trim(),
        full_name: formName.trim(),
        department: formDept.trim() || undefined,
        batch: formBatch.trim() || undefined,
        email: formEmail.trim() || undefined,
        phone: formPhone.trim() || undefined,
      });
    },
    onSuccess: () => {
      setIsCreateOpen(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["students"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      setFormError(err.message);
    },
  });

  // Update Student Mutation
  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedStudent) return;
      return apiClient.patch<StudentItem>(`/v1/students/${selectedStudent.student_id}`, {
        full_name: formName.trim(),
        department: formDept.trim() || undefined,
        batch: formBatch.trim() || undefined,
        email: formEmail.trim() || undefined,
        phone: formPhone.trim() || undefined,
        status: formStatus,
      });
    },
    onSuccess: () => {
      setIsEditOpen(false);
      setSelectedStudent(null);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["students"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      setFormError(err.message);
    },
  });

  // Delete/Deactivate Student Mutation
  const deleteMutation = useMutation({
    mutationFn: async (studentId: string) => {
      return apiClient.delete<StudentItem>(`/v1/students/${studentId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["students"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      alert(`Deactivation failed: ${err.message}`);
    },
  });

  const resetForm = () => {
    setFormId("");
    setFormName("");
    setFormDept("Computer Science & Engineering");
    setFormBatch("2024");
    setFormEmail("");
    setFormPhone("");
    setFormStatus("active");
    setFormError(null);
  };

  const openEditModal = (student: StudentItem) => {
    setSelectedStudent(student);
    setFormId(student.student_id);
    setFormName(student.full_name);
    setFormDept(student.department || "Computer Science & Engineering");
    setFormBatch(student.batch || "2024");
    setFormEmail(student.email || "");
    setFormPhone(student.phone || "");
    setFormStatus(student.status);
    setFormError(null);
    setIsEditOpen(true);
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return "N/A";
    try {
      return new Date(isoString).toLocaleDateString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  const departmentsList = [
    "ALL",
    "Computer Science & Engineering",
    "Electrical & Electronic Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Business Administration",
  ];

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Student Management"
        description="Directory of institutional students and their biometric template enrollment status."
        actions={
          <div className="flex items-center gap-2">
            <Link href="/enrollment">
              <Button size="sm" className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5">
                <Camera className="h-3.5 w-3.5" />
                Biometric Enrollment
              </Button>
            </Link>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => {
                resetForm();
                setIsCreateOpen(true);
              }}
            >
              <Plus className="h-3.5 w-3.5" />
              Register Profile
            </Button>
          </div>
        }
      />

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search by student name or student ID..."
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="pl-9 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-800"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Department selector */}
          <div className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
            <Filter className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={departmentFilter}
              onChange={(e) => {
                setDepartmentFilter(e.target.value);
                setPage(1);
              }}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
            >
              {departmentsList.map((d) => (
                <option key={d} value={d}>
                  {d === "ALL" ? "All Departments" : d}
                </option>
              ))}
            </select>
          </div>

          {/* Status selector */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
          >
            <option value="ALL">All Status</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            className="h-8 px-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            title="Refresh list"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to load students directory: {error instanceof Error ? error.message : "Service error"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetch()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Students Data Table */}
      <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider dark:bg-slate-900 dark:border-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-5 py-3.5">Student ID</th>
                <th className="px-5 py-3.5">Full Name</th>
                <th className="px-5 py-3.5">Department</th>
                <th className="px-5 py-3.5">Batch</th>
                <th className="px-5 py-3.5">Biometrics</th>
                <th className="px-5 py-3.5">Check-Ins</th>
                <th className="px-5 py-3.5">Status</th>
                <th className="px-5 py-3.5">Enrolled Date</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, idx) => (
                  <tr key={idx}>
                    <td colSpan={9} className="px-5 py-3">
                      <Skeleton className="h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : !data || data.students.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-5 py-12 text-center text-slate-500 dark:text-slate-400">
                    <p className="font-semibold text-sm">No students found</p>
                    <p className="text-xs text-slate-400 mt-1">
                      {debouncedSearch
                        ? `No records matching "${debouncedSearch}". Try a different search query.`
                        : "Click 'Register Profile' or 'Biometric Enrollment' to add your first student."}
                    </p>
                  </td>
                </tr>
              ) : (
                data.students.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <td className="px-5 py-3.5 font-mono font-medium text-slate-900 dark:text-slate-100">
                      {s.student_id}
                    </td>
                    <td className="px-5 py-3.5 font-medium text-slate-900 dark:text-slate-100">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 font-semibold text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                          {s.full_name.charAt(0)}
                        </div>
                        <div>
                          <div>{s.full_name}</div>
                          {s.email && <div className="text-[10px] text-slate-400">{s.email}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-300">
                      {s.department || "Unassigned"}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-600 dark:text-slate-300">
                      {s.batch || "—"}
                    </td>
                    <td className="px-5 py-3.5">
                      {s.embeddings_count > 0 ? (
                        <Badge variant="success" className="gap-1 text-[11px] font-medium">
                          <CheckCircle2 className="h-3 w-3" />
                          Enrolled ({s.embeddings_count})
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[11px] text-amber-600 border-amber-300 dark:border-amber-700 dark:text-amber-400">
                          Unenrolled
                        </Badge>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-300">
                      <div className="flex items-center gap-1 font-semibold">
                        <Clock className="h-3.5 w-3.5 text-slate-400" />
                        <span>{s.attendance_count}</span>
                      </div>
                      {s.last_attendance_at && (
                        <div className="text-[10px] text-slate-400">
                          Last: {formatDate(s.last_attendance_at)}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge
                        variant={s.status === "active" ? "success" : "secondary"}
                        className="text-[11px] font-medium"
                      >
                        {s.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 font-mono text-[11px]">
                      {formatDate(s.created_at)}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditModal(s)}
                          className="h-7 w-7 p-0 text-slate-500 hover:text-slate-900 dark:hover:text-slate-100"
                          title="Edit profile"
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Deactivate student ${s.student_id} (${s.full_name})? Biometric templates will be disabled.`)) {
                              deleteMutation.mutate(s.student_id);
                            }
                          }}
                          className="h-7 w-7 p-0 text-rose-500 hover:text-rose-700 dark:hover:text-rose-400"
                          title="Deactivate student"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Toolbar */}
        {data && data.total > pageSize && (
          <div className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900 text-xs">
            <span className="text-slate-500">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, data.total)} of {data.total} students
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

      {/* Register Profile Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <Card className="w-full max-w-md bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-indigo-600" />
                <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                  Register New Student Profile
                </h3>
              </div>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              className="p-6 space-y-4 text-xs"
            >
              {formError && (
                <div className="rounded-md bg-rose-50 p-2.5 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                  {formError}
                </div>
              )}

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">
                  Student ID <span className="text-rose-500">*</span>
                </label>
                <Input
                  required
                  placeholder="e.g. STU-2024-042"
                  value={formId}
                  onChange={(e) => setFormId(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">
                  Full Legal Name <span className="text-rose-500">*</span>
                </label>
                <Input
                  required
                  placeholder="e.g. Tanvir Hossain"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700 dark:text-slate-300">Department</label>
                  <Input
                    placeholder="e.g. CSE"
                    value={formDept}
                    onChange={(e) => setFormDept(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700 dark:text-slate-300">Batch / Year</label>
                  <Input
                    placeholder="e.g. 2024"
                    value={formBatch}
                    onChange={(e) => setFormBatch(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Email Address</label>
                <Input
                  type="email"
                  placeholder="student@university.edu"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Phone</label>
                <Input
                  placeholder="+880 1700 000000"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsCreateOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={createMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
                >
                  {createMutation.isPending && <RefreshCw className="h-3 w-3 animate-spin" />}
                  Register Student
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Edit Profile Modal */}
      {isEditOpen && selectedStudent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <Card className="w-full max-w-md bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
              <div className="flex items-center gap-2">
                <Edit2 className="h-4 w-4 text-indigo-600" />
                <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                  Update Student ({selectedStudent.student_id})
                </h3>
              </div>
              <button
                onClick={() => setIsEditOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate();
              }}
              className="p-6 space-y-4 text-xs"
            >
              {formError && (
                <div className="rounded-md bg-rose-50 p-2.5 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                  {formError}
                </div>
              )}

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Full Legal Name</label>
                <Input
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700 dark:text-slate-300">Department</label>
                  <Input
                    value={formDept}
                    onChange={(e) => setFormDept(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700 dark:text-slate-300">Batch</label>
                  <Input
                    value={formBatch}
                    onChange={(e) => setFormBatch(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Email Address</label>
                <Input
                  type="email"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Status</label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value)}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsEditOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={updateMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
                >
                  {updateMutation.isPending && <RefreshCw className="h-3 w-3 animate-spin" />}
                  Save Changes
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}