"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Volume2, VolumeX, Pause, Play, AlertCircle, RefreshCw, Clock } from "lucide-react";
import { apiClient } from "@/lib/api-client";
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
}

interface AttendanceListResponse {
  total: number;
  records: AttendanceRecord[];
}

export default function LiveAttendancePage() {
  const [isLive, setIsLive] = useState(true);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const knownIdsRef = useRef<Set<string>>(new Set());
  const initialLoadRef = useRef(true);
  const [newlyArrivedIds, setNewlyArrivedIds] = useState<Set<string>>(new Set());

  // Real-time WebSocket connection for instant event triggers
  useAttendanceRealtime();

  // Web Audio API Synthesizer for Chime
  const playChime = () => {
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const now = ctx.currentTime;

      // Note 1: E5 (659.25 Hz)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(659.25, now);
      gain1.gain.setValueAtTime(0.12, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.3);

      // Note 2: B5 (987.77 Hz)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(987.77, now + 0.12);
      gain2.gain.setValueAtTime(0.15, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.5);
    } catch {
      // Audio context might be restricted before first user interaction
    }
  };

  // TanStack Query polling with 2.5s interval
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    dataUpdatedAt,
  } = useQuery<AttendanceListResponse>({
    queryKey: ["live-attendance"],
    queryFn: async () => {
      // Get today's recent attendance records
      return apiClient.get<AttendanceListResponse>("/v1/attendance?limit=30");
    },
    refetchInterval: isLive ? 2500 : false,
    staleTime: 2000,
  });

  // Track new arrivals and trigger chime
  useEffect(() => {
    if (!data || !data.records) return;

    if (initialLoadRef.current) {
      // On initial load, record existing IDs without chiming
      data.records.forEach((r) => knownIdsRef.current.add(r.id));
      initialLoadRef.current = false;
      return;
    }

    const currentRecords = data.records;
    const freshIds = new Set<string>();

    for (const r of currentRecords) {
      if (!knownIdsRef.current.has(r.id)) {
        freshIds.add(r.id);
        knownIdsRef.current.add(r.id);
      }
    }

    if (freshIds.size > 0) {
      setTimeout(() => {
        setNewlyArrivedIds((prev) => new Set([...prev, ...freshIds]));
      }, 0);
      if (audioEnabled) {
        playChime();
      }
    }
  }, [data, audioEnabled]);

  const formatRelativeTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

      if (diffSec < 5) return "Just now";
      if (diffSec < 60) return `${diffSec} seconds ago`;
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin} min${diffMin > 1 ? "s" : ""} ago`;
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoString;
    }
  };

  const formatExactTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Live Attendance Stream"
        description="Real-time biometric recognition events transmitted from classroom edge nodes."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAudioEnabled(!audioEnabled)}
              className="gap-1.5 text-xs text-slate-700 dark:text-slate-200"
            >
              {audioEnabled ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
              {audioEnabled ? "Chime On" : "Muted"}
            </Button>
            <Button
              variant={isLive ? "outline" : "default"}
              size="sm"
              onClick={() => setIsLive(!isLive)}
              className="gap-1.5 text-xs"
            >
              {isLive ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {isLive ? "Pause Polling" : "Resume Stream"}
            </Button>
            <Badge
              variant={isLive ? "success" : "secondary"}
              className="gap-1.5 py-1 px-2.5"
            >
              {isLive ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span>2.5s Polling Active</span>
                </>
              ) : (
                <span>Polling Paused</span>
              )}
            </Badge>
          </div>
        }
      />

      {/* Error Banner */}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              Failed to refresh live stream: {error instanceof Error ? error.message : "Backend unavailable"}
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => refetch()} className="gap-1 text-xs">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        </div>
      )}

      {/* Stream Status Info */}
      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <div>
          Total attendance events logged today:{" "}
          <strong className="text-slate-900 dark:text-slate-100">{data?.total ?? 0}</strong>
        </div>
        {dataUpdatedAt > 0 && (
          <div className="text-[11px] text-slate-400">
            Last polled: {new Date(dataUpdatedAt).toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* Live Stream Cards */}
      <div className="space-y-3">
        {isLoading ? (
          <>
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
          </>
        ) : !data || data.records.length === 0 ? (
          <Card className="border-dashed border-2 border-slate-200 dark:border-slate-800 p-8 text-center">
            <CardContent className="space-y-2 p-0">
              <Clock className="h-8 w-8 text-slate-400 mx-auto stroke-1" />
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                No Attendance Events Yet Today
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                When students approach an ESP32-S3 edge camera, face matches verified by ArcFace will appear here automatically.
              </p>
            </CardContent>
          </Card>
        ) : (
          data.records.map((event) => {
            const isNew = newlyArrivedIds.has(event.id);
            return (
              <Card
                key={event.id}
                className={`border-l-4 transition-all duration-500 ${
                  isNew
                    ? "border-l-emerald-500 bg-emerald-50/30 shadow-md dark:bg-emerald-950/20"
                    : "border-l-indigo-500"
                }`}
              >
                <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-sm dark:bg-indigo-950 dark:text-indigo-300">
                      {event.student_name_snapshot.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                          {event.student_name_snapshot}
                        </span>
                        <span className="font-mono text-xs text-slate-400">
                          ({event.student_id_snapshot})
                        </span>
                        {isNew && (
                          <Badge variant="success" className="text-[10px] py-0 px-1.5 animate-pulse">
                            NEW
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        {event.department || "Academic Department"}
                        {" • "}
                        {event.device_name || event.device_code || (event.device_id ? `Device ${event.device_id.slice(0, 8)}` : "Edge Node")}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between sm:justify-end gap-4 w-full sm:w-auto border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-100 dark:border-slate-800">
                    <div className="text-left sm:text-right">
                      <div className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                        {formatRelativeTime(event.check_in_time)}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        {formatExactTime(event.check_in_time)}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge variant="success" className="text-xs font-medium">
                        {event.recognition_confidence !== null
                          ? `${(event.recognition_confidence * 100).toFixed(1)}% Match`
                          : "100.0% Match"}
                      </Badge>
                      <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-semibold">
                        {event.status}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}