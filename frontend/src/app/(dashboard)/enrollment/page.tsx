"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Camera,
  Upload,
  ShieldCheck,
  CheckCircle2,
  Trash2,
  VideoOff,
  AlertCircle,
  Loader2,
  RefreshCw,
  UserCheck,
  Radio,
  Cpu,
  Monitor,
  FolderUp,
  XCircle,
} from "lucide-react";
import { apiClient, ApiError } from "@/lib/api-client";

interface CapturedSample {
  id: string;
  file: File;
  previewUrl: string;
  source: "webcam" | "upload";
}

interface EnrollmentResult {
  status: string;
  message: string;
  person_id?: string;
  student_id?: string;
  embeddings_count: number;
}

interface DeviceItem {
  id: string;
  device_code: string;
  device_name: string;
  location?: string | null;
  is_active: boolean;
  last_seen_at?: string | null;
}

interface ActiveSessionData {
  session_id: string;
  student_id: string;
  name: string;
  device_code: string;
  target_samples: number;
  collected_count: number;
  status: string;
  expires_in_seconds: number;
}

export default function EnrollmentPage() {
  const queryClient = useQueryClient();

  // Mode selection
  const [acquisitionMode, setAcquisitionMode] = useState<"esp32" | "webcam" | "upload">("esp32");

  // Consent & Student Profile State
  const [consentGiven, setConsentGiven] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [fullName, setFullName] = useState("");
  const [department, setDepartment] = useState("Computer Science & Engineering");
  const [batch, setBatch] = useState("2024");

  // ESP32 Session State
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [selectedDeviceCode, setSelectedDeviceCode] = useState<string>("esp32-cam-01");
  const [targetSamples, setTargetSamples] = useState<number>(3);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [activeSession, setActiveSession] = useState<ActiveSessionData | null>(null);
  const [sessionCountdown, setSessionCountdown] = useState<number>(120);

  // Webcam & Image Acquisition State
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [isStartingCamera, setIsStartingCamera] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [capturedImages, setCapturedImages] = useState<CapturedSample[]>([]);

  // Submission & Result State
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [enrollResult, setEnrollResult] = useState<EnrollmentResult | null>(null);

  // Element and Stream References
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const capturedImagesRef = useRef<CapturedSample[]>([]);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Keep capturedImagesRef in sync for cleanup
  useEffect(() => {
    capturedImagesRef.current = capturedImages;
  }, [capturedImages]);

  // Fetch registered devices on mount
  useEffect(() => {
    async function loadDevices() {
      try {
        const res = await apiClient.get<{ devices: DeviceItem[]; total: number }>("/v1/devices");
        if (res && res.devices) {
          setDevices(res.devices);
          if (res.devices.length > 0 && !selectedDeviceCode) {
            setSelectedDeviceCode(res.devices[0].device_code);
          }
        }
      } catch (err) {
        console.warn("Could not fetch devices list:", err);
      }
    }
    loadDevices();
  }, [selectedDeviceCode]);

  // Clean up MediaStream and Object URLs when component unmounts
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      capturedImagesRef.current.forEach((img) => {
        URL.revokeObjectURL(img.previewUrl);
      });
    };
  }, []);

  // Connect video element to MediaStream when camera becomes active
  useEffect(() => {
    if (isCameraActive && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch((err) => {
        console.error("Video stream playback interrupted:", err);
      });
    }
  }, [isCameraActive]);

  // Active Session countdown timer
  useEffect(() => {
    if (!activeSession || activeSession.status !== "active") return;

    const timer = setInterval(() => {
      setSessionCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setActiveSession(null);
          setSubmitError("ESP32 enrollment session expired. You may start a new session.");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [activeSession]);

  /**
   * Poll active enrollment session state
   */
  const pollSession = useCallback(async (sessionId: string) => {
    try {
      const res = await apiClient.get<ActiveSessionData>(`/v1/face/enroll/session/${sessionId}`);
      if (res) {
        setActiveSession(res);
        if (res.status === "completed") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setEnrollResult({
            status: "success",
            message: `Successfully enrolled ${res.target_samples} face templates via ESP32 camera!`,
            student_id: res.student_id,
            embeddings_count: res.target_samples,
          });
          queryClient.invalidateQueries({ queryKey: ["students"] });
          queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
          setActiveSession(null);
        } else if (res.status === "cancelled" || res.status === "expired") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setActiveSession(null);
          if (res.status === "expired") {
            setSubmitError("Enrollment session timed out.");
          }
        }
      }
    } catch {
      // Ignore polling errors
    }
  }, [queryClient]);

  // Start polling when activeSession is set
  useEffect(() => {
    if (activeSession && activeSession.status === "active") {
      pollIntervalRef.current = setInterval(() => {
        pollSession(activeSession.session_id);
      }, 1500);
    } else {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [activeSession, pollSession]);

  /**
   * Start an authenticated ESP32 enrollment session
   */
  const startEsp32Session = async () => {
    if (!consentGiven) {
      setSubmitError("Institutional biometric consent is mandatory before starting session.");
      return;
    }
    if (!studentId.trim() || !fullName.trim()) {
      setSubmitError("Student ID and Full Name are required.");
      return;
    }
    if (!selectedDeviceCode) {
      setSubmitError("Please select a registered ESP32 edge camera.");
      return;
    }

    setIsStartingSession(true);
    setSubmitError(null);
    setEnrollResult(null);

    try {
      const res = await apiClient.post<ActiveSessionData>("/v1/face/enroll/session", {
        student_id: studentId.trim(),
        name: fullName.trim(),
        department: department.trim() || null,
        batch: batch.trim() || null,
        device_code: selectedDeviceCode,
        target_samples: targetSamples,
        consent_confirmed: true,
      });

      setActiveSession(res);
      setSessionCountdown(res.expires_in_seconds || 120);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Failed to initiate ESP32 enrollment session.");
      }
    } finally {
      setIsStartingSession(false);
    }
  };

  /**
   * Cancel the active ESP32 enrollment session
   */
  const cancelEsp32Session = async () => {
    if (!activeSession) return;
    try {
      await apiClient.delete(`/v1/face/enroll/session/${activeSession.session_id}`);
      setActiveSession(null);
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    } catch (err) {
      console.error("Failed to cancel session:", err);
    }
  };

  /**
   * Launch webcam using exact navigator.mediaDevices.getUserMedia API
   */
  const startCamera = async () => {
    setCameraError(null);
    setSubmitError(null);
    setIsStartingCamera(true);

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        "Webcam access is not supported by your browser or the site is not served in a secure context (HTTPS / localhost)."
      );
      setIsStartingCamera(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });

      streamRef.current = stream;
      setIsCameraActive(true);
    } catch (err: unknown) {
      const error = err as Error & { name?: string };
      if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
        setCameraError(
          "Camera access permission was denied. Please allow camera permissions in your browser address bar and try again."
        );
      } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
        setCameraError(
          "No webcam device was found on your system. You can switch to ESP32 Edge Camera or Upload Files."
        );
      } else if (error.name === "NotReadableError" || error.name === "TrackStartError") {
        setCameraError(
          "The webcam is currently in use by another application. Please close any software using the camera and retry."
        );
      } else if (error.name === "OverconstrainedError") {
        setCameraError(
          "No compatible webcam stream was found matching the requested constraints."
        );
      } else {
        setCameraError(
          `Unable to access webcam: ${error.message || "Unknown hardware error."}`
        );
      }
      setIsCameraActive(false);
    } finally {
      setIsStartingCamera(false);
    }
  };

  /**
   * Stop all MediaStream tracks and reset camera states
   */
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
  };

  /**
   * Capture a single video frame via Canvas and convert to JPEG File
   */
  const capturePhoto = () => {
    if (!videoRef.current || !isCameraActive) return;
    if (capturedImages.length >= 5) {
      setCameraError("Maximum 5 facial captures reached. Remove an image to take a new one.");
      return;
    }

    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const filename = `webcam_${Date.now()}_${capturedImages.length + 1}.jpg`;
        const file = new File([blob], filename, { type: "image/jpeg" });
        const previewUrl = URL.createObjectURL(blob);

        setCapturedImages((prev) => [
          ...prev,
          {
            id: Math.random().toString(36).substring(2, 9),
            file,
            previewUrl,
            source: "webcam",
          },
        ]);
        setCameraError(null);
      },
      "image/jpeg",
      0.95
    );
  };

  /**
   * Handle browsing and adding external photo files
   */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const remainingSlots = 5 - capturedImages.length;
    if (remainingSlots <= 0) {
      setCameraError("Maximum 5 facial captures reached. Remove an image to add more.");
      return;
    }

    const newSamples: CapturedSample[] = [];
    const filesToAdd = Array.from(files).slice(0, remainingSlots);

    for (const file of filesToAdd) {
      if (!file.type.startsWith("image/")) continue;
      const previewUrl = URL.createObjectURL(file);
      newSamples.push({
        id: Math.random().toString(36).substring(2, 9),
        file,
        previewUrl,
        source: "upload",
      });
    }

    setCapturedImages((prev) => [...prev, ...newSamples]);
    setCameraError(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  /**
   * Remove a single captured photo and revoke its object URL
   */
  const removeImage = (id: string) => {
    setCapturedImages((prev) => {
      const target = prev.find((img) => img.id === id);
      if (target) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((img) => img.id !== id);
    });
  };

  /**
   * Submit manual enrollment request (for Webcam or File Upload)
   */
  const handleEnrollManual = async () => {
    if (!consentGiven) {
      setSubmitError("Institutional biometric consent is mandatory before enrolling.");
      return;
    }
    if (!studentId.trim() || !fullName.trim()) {
      setSubmitError("Student ID and Full Name are required fields.");
      return;
    }
    if (capturedImages.length === 0) {
      setSubmitError("Please capture or upload at least 1 facial image (3 to 5 recommended).");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setEnrollResult(null);

    try {
      const formData = new FormData();
      formData.append("student_id", studentId.trim());
      formData.append("name", fullName.trim());
      if (department.trim()) formData.append("department", department.trim());
      if (batch.trim()) formData.append("batch", batch.trim());

      for (const sample of capturedImages) {
        formData.append("images", sample.file, sample.file.name);
      }

      const res = await apiClient.post<EnrollmentResult>("/v1/face/enroll", formData);
      setEnrollResult(res);
      queryClient.invalidateQueries({ queryKey: ["students"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      stopCamera();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Biometric template extraction failed. Please ensure images meet quality standards.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  /**
   * Reset the form to enroll another student
   */
  const handleResetForNextStudent = () => {
    capturedImages.forEach((img) => URL.revokeObjectURL(img.previewUrl));
    setCapturedImages([]);
    setEnrollResult(null);
    setSubmitError(null);
    setCameraError(null);
    setActiveSession(null);
    setConsentGiven(false);
    setStudentId("");
    setFullName("");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Biometric Face Enrollment Wizard"
        description="Extract and index 512-D ArcFace vectors via ESP32-CAM, local webcam, or digital captures."
      />

      {/* Biometric Ethics & Consent Box */}
      <div className="rounded-lg border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/30">
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-5 w-5 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <div className="space-y-2 text-xs text-indigo-950 dark:text-indigo-200">
            <p className="font-semibold text-sm">
              Institutional Biometric Data Privacy & Consent Notice
            </p>
            <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
              In compliance with data protection standards, raw facial images are processed in-memory for 5-point landmark alignment and 512-dimensional numerical embedding vector extraction. <strong>No raw camera bitmaps or photographs are permanently stored in the database.</strong>
            </p>
            <label className="flex items-center gap-2 pt-1 font-medium text-slate-800 dark:text-slate-200 cursor-pointer">
              <input
                type="checkbox"
                checked={consentGiven}
                onChange={(e) => setConsentGiven(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span>Student has confirmed identity and authorized biometric feature registration for academic attendance verification.</span>
            </label>
          </div>
        </div>
      </div>

      {/* Enrollment Result Card */}
      {enrollResult && (
        <Card className="border-emerald-200 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/20">
          <CardContent className="pt-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/60 dark:text-emerald-400">
                  <UserCheck className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-emerald-900 dark:text-emerald-200">
                    Biometric Templates Successfully Indexed
                  </h4>
                  <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-0.5">
                    Student ID: <span className="font-semibold">{enrollResult.student_id}</span> • {enrollResult.embeddings_count} ArcFace vectors committed to pgvector.
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleResetForNextStudent}
                className="gap-1.5 border-emerald-300 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-900/40"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Enroll Another Student
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Submission Error Banner */}
      {submitError && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50/80 p-4 text-xs text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold">Enrollment Notice</p>
            <p>{submitError}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Step 1: Student Profile Form */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">1. Student Profile</CardTitle>
              <Badge variant="outline">Step 1 of 3</Badge>
            </div>
            <CardDescription>
              Assign the biometric template to an active university ID.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Student ID *
              </label>
              <Input
                placeholder="e.g. STU-2024-001"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                disabled={activeSession !== null}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Full Name *
              </label>
              <Input
                placeholder="e.g. Rahim Ahmed"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={activeSession !== null}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Academic Department
              </label>
              <Input
                placeholder="e.g. Computer Science & Engineering"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                disabled={activeSession !== null}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Batch / Academic Year
              </label>
              <Input
                placeholder="e.g. 2024"
                value={batch}
                onChange={(e) => setBatch(e.target.value)}
                disabled={activeSession !== null}
              />
            </div>
          </CardContent>
        </Card>

        {/* Step 2: Acquisition Selector & Implementation */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">2. Biometric Image Acquisition</CardTitle>
              <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs dark:border-slate-800 dark:bg-slate-900">
                <button
                  type="button"
                  onClick={() => {
                    setAcquisitionMode("esp32");
                    stopCamera();
                  }}
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1 font-medium transition-colors ${
                    acquisitionMode === "esp32"
                      ? "bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400"
                      : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
                  }`}
                >
                  <Cpu className="h-3.5 w-3.5" />
                  ESP32 Camera
                </button>
                <button
                  type="button"
                  onClick={() => setAcquisitionMode("webcam")}
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1 font-medium transition-colors ${
                    acquisitionMode === "webcam"
                      ? "bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400"
                      : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
                  }`}
                >
                  <Monitor className="h-3.5 w-3.5" />
                  PC Webcam
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAcquisitionMode("upload");
                    stopCamera();
                  }}
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1 font-medium transition-colors ${
                    acquisitionMode === "upload"
                      ? "bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400"
                      : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
                  }`}
                >
                  <FolderUp className="h-3.5 w-3.5" />
                  Upload
                </button>
              </div>
            </div>
            <CardDescription>
              {acquisitionMode === "esp32"
                ? "Enroll directly through a physical ESP32-S3-CAM edge device."
                : "Capture 3 to 5 clear facial captures with varied angles (frontal, slight left, slight right)."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* ----------------- TAB 1: ESP32 Edge Camera ----------------- */}
            {acquisitionMode === "esp32" && (
              <div className="space-y-4">
                {activeSession ? (
                  <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-5 dark:border-indigo-900/60 dark:bg-indigo-950/40 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex h-3 w-3 relative">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-600" />
                        </span>
                        <h4 className="text-sm font-semibold text-indigo-950 dark:text-indigo-200">
                          Active ESP32 Enrollment Session
                        </h4>
                      </div>
                      <Badge variant="outline" className="border-indigo-300 text-indigo-700 dark:border-indigo-800 dark:text-indigo-300">
                        Expires in: {sessionCountdown}s
                      </Badge>
                    </div>

                    <div className="text-xs text-slate-600 dark:text-slate-300 space-y-1">
                      <p>
                        Camera <span className="font-semibold text-slate-900 dark:text-slate-100">{activeSession.device_code}</span> is actively collecting biometric samples for student <span className="font-semibold text-slate-900 dark:text-slate-100">{activeSession.name} ({activeSession.student_id})</span>.
                      </p>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        Position student in front of camera. Ask them to turn their head slightly between captures.
                      </p>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-1.5 pt-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span>Samples Collected</span>
                        <span className="text-indigo-600 dark:text-indigo-400">
                          {activeSession.collected_count} / {activeSession.target_samples}
                        </span>
                      </div>
                      <div className="h-3 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 transition-all duration-300 rounded-full"
                          style={{
                            width: `${(activeSession.collected_count / activeSession.target_samples) * 100}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Checkmarks */}
                    <div className="flex items-center gap-2 pt-2">
                      {Array.from({ length: activeSession.target_samples }).map((_, idx) => (
                        <div
                          key={idx}
                          className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium border ${
                            idx < activeSession.collected_count
                              ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                              : "border-slate-200 bg-white text-slate-400 dark:border-slate-800 dark:bg-slate-900"
                          }`}
                        >
                          <CheckCircle2 className={`h-3.5 w-3.5 ${idx < activeSession.collected_count ? "text-emerald-600" : "text-slate-300"}`} />
                          <span>Sample #{idx + 1}</span>
                        </div>
                      ))}
                    </div>

                    <div className="pt-2 flex justify-end">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={cancelEsp32Session}
                        className="gap-1.5 text-xs"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Cancel Enrollment Session
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-5 dark:border-slate-800 dark:bg-slate-900/30 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* Device Selector */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          Target ESP32 Edge Device *
                        </label>
                        <select
                          value={selectedDeviceCode}
                          onChange={(e) => setSelectedDeviceCode(e.target.value)}
                          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                        >
                          {devices.length === 0 ? (
                            <option value="esp32-cam-01">esp32-cam-01 (Default Hardware)</option>
                          ) : (
                            devices.map((dev) => (
                              <option key={dev.id} value={dev.device_code}>
                                {dev.device_code} ({dev.device_name}) {dev.is_active ? "● Online" : "○ Inactive"}
                              </option>
                            ))
                          )}
                        </select>
                      </div>

                      {/* Sample Target Selector */}
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          Biometric Sample Target
                        </label>
                        <div className="flex items-center gap-2 pt-0.5">
                          {[3, 4, 5].map((count) => (
                            <button
                              key={count}
                              type="button"
                              onClick={() => setTargetSamples(count)}
                              className={`flex-1 rounded border py-1.5 text-xs font-semibold transition-colors ${
                                targetSamples === count
                                  ? "border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-950/60 dark:text-indigo-300"
                                  : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                              }`}
                            >
                              {count} Samples
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950/50 dark:text-slate-400 space-y-1">
                      <p className="font-semibold text-slate-800 dark:text-slate-200">
                        How ESP32 Enrollment Works:
                      </p>
                      <p>
                        1. Clicking below activates enrollment mode on <span className="font-mono text-indigo-600 dark:text-indigo-400 font-semibold">{selectedDeviceCode}</span> for 120 seconds.
                      </p>
                      <p>
                        2. The ESP32 camera TFT screen displays <span className="font-mono text-cyan-600 font-semibold">[ENROLLING 1/{targetSamples}]</span> with the student&apos;s name.
                      </p>
                      <p>
                        3. The edge camera automatically crops and uploads facial frames with 5-point landmarks, checking for duplicate faces and committing to pgvector upon reaching target.
                      </p>
                    </div>

                    <div className="flex justify-end pt-2">
                      <Button
                        onClick={startEsp32Session}
                        disabled={!consentGiven || isStartingSession}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium gap-1.5 shadow-sm"
                      >
                        {isStartingSession ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Initiating Session...
                          </>
                        ) : (
                          <>
                            <Radio className="h-4 w-4" />
                            Start ESP32 Enrollment Session
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ----------------- TAB 2: PC Webcam ----------------- */}
            {acquisitionMode === "webcam" && (
              <div className="space-y-4">
                {/* Hardware / Permission Camera Alert */}
                {cameraError && (
                  <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
                    <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <p className="font-semibold">Webcam Notice</p>
                      <p>{cameraError}</p>
                    </div>
                  </div>
                )}

                {/* Live Camera Viewfinder or Placeholder Acquisition Box */}
                {isCameraActive ? (
                  <div className="flex flex-col items-center gap-3 rounded-lg border border-slate-300 bg-slate-950 p-4 dark:border-slate-800">
                    <div className="relative w-full max-w-md aspect-[4/3] rounded-md overflow-hidden bg-black flex items-center justify-center border border-slate-800 shadow-inner">
                      {/* Live Video Feed */}
                      <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-full object-cover scale-x-[-1]"
                      />

                      {/* Face Framing Guide Overlay */}
                      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                        <div className="w-44 h-56 rounded-[50%] border-2 border-dashed border-cyan-400/70 bg-cyan-500/5 shadow-[0_0_15px_rgba(6,182,212,0.2)]" />
                      </div>

                      {/* Live Recording Indicator */}
                      <div className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-slate-900/80 px-2.5 py-1 text-[10px] font-medium text-white backdrop-blur">
                        <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                        WEBCAM LIVE
                      </div>

                      {/* Capture Count Overlay */}
                      <div className="absolute top-3 right-3 rounded-full bg-slate-900/80 px-2.5 py-1 text-[10px] font-medium text-slate-200 backdrop-blur">
                        {capturedImages.length} / 5 Samples
                      </div>
                    </div>

                    {/* Webcam Controls */}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        onClick={capturePhoto}
                        disabled={capturedImages.length >= 5}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white gap-1.5 shadow-sm"
                      >
                        <Camera className="h-3.5 w-3.5" />
                        Capture Photo ({capturedImages.length}/5)
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={stopCamera}
                        className="gap-1.5 border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
                      >
                        <VideoOff className="h-3.5 w-3.5" />
                        Stop Camera
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex min-h-[200px] flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50/60 p-6 text-center dark:border-slate-800 dark:bg-slate-900/40">
                    <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
                      {isStartingCamera ? (
                        <Loader2 className="h-6 w-6 animate-spin" />
                      ) : (
                        <Camera className="h-6 w-6" />
                      )}
                    </div>
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      Browser Webcam Feed
                    </h4>
                    <p className="mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">
                      Start local camera to capture biometric face crops directly through this computer.
                    </p>
                    <div className="mt-4">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={startCamera}
                        disabled={isStartingCamera || capturedImages.length >= 5}
                        className="gap-1.5"
                      >
                        {isStartingCamera ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Connecting...
                          </>
                        ) : (
                          <>
                            <Camera className="h-3.5 w-3.5" />
                            Launch Webcam
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ----------------- TAB 3: Upload Files ----------------- */}
            {acquisitionMode === "upload" && (
              <div className="space-y-4">
                <input
                  type="file"
                  ref={fileInputRef}
                  accept="image/jpeg,image/png"
                  multiple
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50/60 p-6 text-center transition-colors hover:bg-slate-100/60 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:bg-slate-900/60"
                >
                  <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
                    <Upload className="h-6 w-6" />
                  </div>
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Upload Pre-Captured Facial Photographs
                  </h4>
                  <p className="mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">
                    Click to browse or drop 1-5 JPEG/PNG images (clear frontal and side angles).
                  </p>
                </div>
              </div>
            )}

            {/* Captured Samples Gallery (for Webcam and Upload modes) */}
            {acquisitionMode !== "esp32" && capturedImages.length > 0 && (
              <div className="space-y-2.5 pt-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    Acquired Biometric Samples ({capturedImages.length} of 5)
                  </span>
                  {capturedImages.length < 3 ? (
                    <span className="text-amber-600 dark:text-amber-400 text-[11px]">
                      Recommended: At least 3 photos with diverse angles
                    </span>
                  ) : (
                    <span className="text-emerald-600 dark:text-emerald-400 text-[11px] font-medium">
                      ✓ Optimal template quantity
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                  {capturedImages.map((img, idx) => (
                    <div
                      key={img.id}
                      className="group relative rounded-md border border-slate-200 bg-white p-1.5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={img.previewUrl}
                        alt={`Sample ${idx + 1}`}
                        className="h-24 w-full rounded object-cover"
                      />
                      <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                        <span>#{idx + 1} ({img.source})</span>
                        <button
                          type="button"
                          onClick={() => removeImage(img.id)}
                          className="rounded p-0.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400 transition-colors"
                          title="Remove image"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quality Standards Checklist */}
            <div className="grid grid-cols-2 gap-3 pt-2 text-[11px] text-slate-600 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                <span>Sharp focus (Laplacian Var &gt; 50.0)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                <span>Balanced lighting (25.0 - 235.0)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                <span>5-point facial landmark alignment</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                <span>Duplicate face check via pgvector</span>
              </div>
            </div>

            {/* Step 3: Action Submission for Webcam / Upload */}
            {acquisitionMode !== "esp32" && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-100 dark:border-slate-800">
                <div className="text-xs text-slate-500">
                  {!consentGiven ? (
                    <span className="text-amber-600 dark:text-amber-400 font-medium">
                      Consent checkbox required above to proceed.
                    </span>
                  ) : capturedImages.length === 0 ? (
                    <span>Acquire at least 1 photo to enable enrollment.</span>
                  ) : (
                    <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                      Ready to compute embeddings ({capturedImages.length} sample{capturedImages.length > 1 ? "s" : ""}).
                    </span>
                  )}
                </div>

                <Button
                  onClick={handleEnrollManual}
                  disabled={!consentGiven || capturedImages.length === 0 || isSubmitting}
                  className="w-full sm:w-auto bg-indigo-600 hover:bg-indigo-500 text-white font-medium gap-1.5"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Computing 512-D Vectors...
                    </>
                  ) : (
                    "Compute & Enroll Biometric Templates"
                  )}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
