"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Plus,
  KeyRound,
  AlertCircle,
  RefreshCw,
  Copy,
  Check,
  X,
  Activity,
  Trash2,
  RotateCw,
  Power,
  ShieldCheck,
} from "lucide-react";
import { apiClient, ApiError } from "@/lib/api-client";

interface DeviceItem {
  id: string;
  device_name: string;
  device_code: string;
  location: string | null;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
  is_online: boolean;
}

interface DeviceListResponse {
  total: number;
  devices: DeviceItem[];
}

interface DeviceRegistrationResponse {
  device: DeviceItem;
  plaintext_api_key: string;
  message: string;
}

interface DeviceKeyRotationResponse {
  device_id: string;
  device_code: string;
  plaintext_api_key: string;
  message: string;
}

export default function DevicesPage() {
  const queryClient = useQueryClient();

  // Modals state
  const [isProvisionOpen, setIsProvisionOpen] = useState(false);
  const [createdKeyInfo, setCreatedKeyInfo] = useState<{
    code: string;
    key: string;
    isRotation?: boolean;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  // Provision Form state
  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formLocation, setFormLocation] = useState("");
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [heartbeatSending, setHeartbeatSending] = useState<string | null>(null);

  // TanStack Query for Devices
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<DeviceListResponse>({
    queryKey: ["devices"],
    queryFn: () => apiClient.get<DeviceListResponse>("/v1/devices?limit=50"),
    refetchInterval: 10000,
  });

  // Provision Mutation
  const provisionMutation = useMutation({
    mutationFn: async () => {
      return apiClient.post<DeviceRegistrationResponse>("/v1/devices", {
        device_code: formCode.trim(),
        device_name: formName.trim(),
        location: formLocation.trim() || undefined,
      });
    },
    onSuccess: (res) => {
      setIsProvisionOpen(false);
      setFormCode("");
      setFormName("");
      setFormLocation("");
      setProvisionError(null);
      setCreatedKeyInfo({
        code: res.device.device_code,
        key: res.plaintext_api_key,
        isRotation: false,
      });
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      setProvisionError(err.message);
    },
  });

  // Rotate Key Mutation
  const rotateKeyMutation = useMutation({
    mutationFn: async (deviceId: string) => {
      return apiClient.post<DeviceKeyRotationResponse>(`/v1/devices/${deviceId}/rotate-key`);
    },
    onSuccess: (res) => {
      setCreatedKeyInfo({
        code: res.device_code,
        key: res.plaintext_api_key,
        isRotation: true,
      });
      queryClient.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (err: ApiError) => {
      alert(`Key rotation failed: ${err.message}`);
    },
  });

  // Toggle Active Mutation
  const toggleActiveMutation = useMutation({
    mutationFn: async ({ id, isActive }: { id: string; isActive: boolean }) => {
      return apiClient.patch<DeviceItem>(`/v1/devices/${id}`, {
        is_active: isActive,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      alert(`Status update failed: ${err.message}`);
    },
  });

  // Delete/Deactivate Mutation
  const deleteMutation = useMutation({
    mutationFn: async (deviceId: string) => {
      return apiClient.delete(`/v1/devices/${deviceId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err: ApiError) => {
      alert(`Deactivation failed: ${err.message}`);
    },
  });

  // Test Heartbeat
  const handleTestHeartbeat = async (deviceCode: string) => {
    try {
      setHeartbeatSending(deviceCode);
      await apiClient.post(`/v1/devices/heartbeat?device_code=${deviceCode}`);
      await refetch();
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    } catch (err) {
      alert(`Heartbeat ping failed: ${err instanceof Error ? err.message : "Error"}`);
    } finally {
      setHeartbeatSending(null);
    }
  };

  const handleCopyKey = () => {
    if (!createdKeyInfo) return;
    navigator.clipboard.writeText(createdKeyInfo.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatLastSeen = (isoString?: string | null) => {
    if (!isoString) return "Never connected";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

      if (diffSec < 5) return "Just now";
      if (diffSec < 60) return `${diffSec} seconds ago`;
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin} min${diffMin > 1 ? "s" : ""} ago`;
      const diffHours = Math.floor(diffMin / 60);
      if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
      return date.toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Edge Camera Nodes"
        description="Provision and monitor ESP32-S3-CAM biometric edge sensors and hardware nodes."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="gap-1.5 text-xs text-slate-700 dark:text-slate-200"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setProvisionError(null);
                setIsProvisionOpen(true);
              }}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
            >
              <Plus className="h-3.5 w-3.5" />
              Provision Edge Device
            </Button>
          </div>
        }
      />

      {/* Security Banner */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start gap-3">
          <KeyRound className="h-5 w-5 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <div className="text-xs space-y-1">
            <div className="font-semibold text-slate-900 dark:text-slate-100">
              Bcrypt Cryptographic Authentication Guard & Telemetry Window
            </div>
            <p className="text-slate-500 dark:text-slate-400">
              Each ESP32 node communicates via a pre-shared <code>X-Device-Api-Key</code>. The backend verifies hashes using bcrypt (rounds=12). A device is marked <strong>ONLINE</strong> strictly if a valid heartbeat or recognition query was received within the documented 120-second window. Plaintext API keys are never stored in the database or exposed in list queries.
            </p>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to load edge camera devices: {error instanceof Error ? error.message : "Service error"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetch()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Edge Devices Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {isLoading ? (
          <>
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </>
        ) : !data || data.devices.length === 0 ? (
          <div className="col-span-3 py-12 text-center text-slate-500 dark:text-slate-400 border border-dashed rounded-xl">
            <p className="font-semibold text-sm">No edge devices registered yet</p>
            <p className="text-xs text-slate-400 mt-1">
              Click &apos;Provision Edge Device&apos; above to register your first ESP32 camera node.
            </p>
          </div>
        ) : (
          data.devices.map((node) => (
            <Card key={node.id} className="border-slate-200 dark:border-slate-800 flex flex-col justify-between">
              <div>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <Badge
                      variant={node.is_online ? "success" : "secondary"}
                      className="gap-1 text-[10px]"
                    >
                      {node.is_online && (
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      )}
                      {node.is_online ? "ONLINE" : "OFFLINE"}
                    </Badge>
                    <span className="font-mono text-[11px] text-slate-400">{node.device_code}</span>
                  </div>
                  <CardTitle className="text-sm font-semibold mt-2">{node.device_name}</CardTitle>
                  <CardDescription className="text-xs">{node.location || "Academic Facility"}</CardDescription>
                </CardHeader>

                <CardContent className="space-y-2.5 pt-0 text-xs text-slate-600 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800 mt-2">
                  <div className="flex items-center justify-between pt-2">
                    <span>Node Status</span>
                    <Badge variant={node.is_active ? "success" : "outline"} className="text-[10px]">
                      {node.is_active ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Hardware Profile</span>
                    <span className="font-medium text-slate-800 dark:text-slate-200">
                      ESP32-S3-CAM (OV2640)
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Last Telemetry</span>
                    <span className="font-medium text-slate-800 dark:text-slate-200">
                      {formatLastSeen(node.last_seen_at)}
                    </span>
                  </div>
                </CardContent>
              </div>

              {/* Action Toolbar on Card Footer */}
              <div className="p-4 pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-1 text-xs">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleTestHeartbeat(node.device_code)}
                  disabled={heartbeatSending === node.device_code || !node.is_active}
                  className="h-7 text-[11px] gap-1"
                  title="Simulate edge node heartbeat"
                >
                  <Activity className={`h-3 w-3 text-emerald-600 ${heartbeatSending === node.device_code ? "animate-spin" : ""}`} />
                  Ping
                </Button>

                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Rotate API key for ${node.device_code}? ESP32 node must be reflashed with the new key.`)) {
                        rotateKeyMutation.mutate(node.id);
                      }
                    }}
                    className="h-7 px-2 text-[11px] text-slate-600 dark:text-slate-300 gap-1"
                    title="Rotate device secret key"
                  >
                    <RotateCw className="h-3 w-3" />
                    Key
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      toggleActiveMutation.mutate({ id: node.id, isActive: !node.is_active })
                    }
                    className={`h-7 px-2 text-[11px] gap-1 ${node.is_active ? "text-amber-600 hover:text-amber-700" : "text-emerald-600 hover:text-emerald-700"}`}
                    title={node.is_active ? "Disable device" : "Activate device"}
                  >
                    <Power className="h-3 w-3" />
                    {node.is_active ? "Disable" : "Enable"}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Deactivate node ${node.device_code}? Existing check-ins remain preserved in ledger.`)) {
                        deleteMutation.mutate(node.id);
                      }
                    }}
                    className="h-7 w-7 p-0 text-rose-500 hover:text-rose-700"
                    title="Deactivate device"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Provision Edge Device Modal */}
      {isProvisionOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <Card className="w-full max-w-md bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-indigo-600" />
                <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                  Provision ESP32 Edge Device
                </h3>
              </div>
              <button
                onClick={() => setIsProvisionOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                provisionMutation.mutate();
              }}
              className="p-6 space-y-4 text-xs"
            >
              {provisionError && (
                <div className="rounded-md bg-rose-50 p-2.5 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
                  {provisionError}
                </div>
              )}

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">
                  Device Code <span className="text-rose-500">*</span>
                </label>
                <Input
                  required
                  placeholder="e.g. esp32-cam-02"
                  value={formCode}
                  onChange={(e) => setFormCode(e.target.value)}
                />
                <p className="text-[11px] text-slate-400">
                  Unique identifier used by ESP32 firmware in telemetry queries.
                </p>
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">
                  Device Name <span className="text-rose-500">*</span>
                </label>
                <Input
                  required
                  placeholder="e.g. CSE Hardware Lab Camera"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700 dark:text-slate-300">Physical Location</label>
                <Input
                  placeholder="e.g. Academic Building 2, Room 304"
                  value={formLocation}
                  onChange={(e) => setFormLocation(e.target.value)}
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsProvisionOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={provisionMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
                >
                  {provisionMutation.isPending && <RefreshCw className="h-3 w-3 animate-spin" />}
                  Provision & Generate Key
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* One-Time Plaintext Key Alert Modal */}
      {createdKeyInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <Card className="w-full max-w-lg bg-white dark:bg-slate-900 border-amber-300 dark:border-amber-700 shadow-2xl border-2">
            <div className="p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                  <KeyRound className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900 dark:text-slate-100">
                    {createdKeyInfo.isRotation ? "Device API Key Rotated" : "Device Provisioned Successfully"}
                  </h3>
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    Copy and flash this plaintext API key to the ESP32 node immediately.
                  </p>
                </div>
              </div>

              <div className="rounded-lg bg-slate-50 dark:bg-slate-950 p-4 border border-slate-200 dark:border-slate-800 space-y-2">
                <div className="text-[11px] font-semibold text-slate-500 uppercase">
                  Device: {createdKeyInfo.code}
                </div>
                <div className="flex items-center justify-between gap-2 bg-white dark:bg-slate-900 p-2.5 rounded border border-slate-300 dark:border-slate-700">
                  <code className="text-xs font-mono text-indigo-600 dark:text-indigo-400 break-all select-all">
                    {createdKeyInfo.key}
                  </code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCopyKey}
                    className="shrink-0 h-7 gap-1 text-xs"
                  >
                    {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>
                <p className="text-[11px] text-slate-500">
                  ⚠️ In accordance with security standards, this plaintext key is shown <strong>ONLY ONCE</strong> and cannot be retrieved later.
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  size="sm"
                  onClick={() => setCreatedKeyInfo(null)}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  I Have Flashed / Saved This Key
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}