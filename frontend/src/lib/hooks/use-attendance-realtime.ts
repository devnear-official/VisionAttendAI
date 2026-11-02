"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

interface RealtimeEvent {
  event: string;
  attendance_id?: string;
  student_id?: string;
  full_name?: string;
  department?: string;
  confidence?: number;
  check_in_time?: string;
  [key: string]: unknown;
}

export function useAttendanceRealtime(options?: {
  onEvent?: (event: RealtimeEvent) => void;
}) {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);
  const onEventRef = useRef(options?.onEvent);
  const connectRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    onEventRef.current = options?.onEvent;
  }, [options?.onEvent]);

  const connect = useCallback(async () => {
    if (!isMountedRef.current) return;
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      const res = await fetch("/api/auth/ws-token");
      if (!res.ok) {
        // Not authenticated or server error
        return;
      }
      const data = await res.json();
      if (!data.token) return;

      const host = window.location.hostname || "127.0.0.1";
      const wsUrl = `ws://${host}:8000/api/v1/ws/attendance?token=${encodeURIComponent(data.token)}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) {
          ws.close();
          return;
        }
        setIsConnected(true);

        // Keepalive ping every 25 seconds
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 25000);
      };

      ws.onmessage = (eventMsg) => {
        try {
          const parsed = JSON.parse(eventMsg.data);
          if (parsed.event === "pong") return;

          setLastEvent(parsed);
          if (onEventRef.current) {
            onEventRef.current(parsed);
          }

          // Instantly invalidate TanStack queries without aggressive polling
          if (
            parsed.event === "attendance_verified" ||
            parsed.event === "attendance_deleted" ||
            parsed.event === "enrollment_completed"
          ) {
            queryClient.invalidateQueries({ queryKey: ["attendance-history"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
            queryClient.invalidateQueries({ queryKey: ["live-attendance"] });
            queryClient.invalidateQueries({ queryKey: ["students"] });
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

        // Attempt reconnect after 3 seconds if still mounted
        if (isMountedRef.current) {
          if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            connectRef.current();
          }, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // Reconnect after brief delay
      if (isMountedRef.current) {
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          connectRef.current();
        }, 4000);
      }
    }
  }, [queryClient]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, lastEvent };
}
