export class ApiError extends Error {
  statusCode: number;
  details?: unknown;

  constructor(message: string, statusCode: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

/**
 * Reads a cookie value by name in client-side environment.
 */
function getClientCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^|;\\s*)(${name})=([^;]*)`));
  return match ? decodeURIComponent(match[3]) : null;
}

/**
 * Base client-side API fetcher that proxies requests through the Next.js BFF route
 * to guarantee that backend ADMIN_API_KEY is never exposed in browser JavaScript.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `/api/proxy${path}`;

  const headers = new Headers(options.headers || {});

  // Automatically attach Content-Type for JSON payloads if not already specified
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  // Enforce CSRF token on mutating requests
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getClientCookie("va_csrf");
    if (!csrfToken) {
      throw new ApiError("CSRF verification token missing. Please refresh and re-authenticate.", 403);
    }
    headers.set("x-csrf-token", csrfToken);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "same-origin", // Include httpOnly session cookie
  });

  // Handle session expiration or unauthorized response globally
  if (response.status === 401 && typeof window !== "undefined") {
    const currentPath = window.location.pathname;
    if (currentPath !== "/login") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = `/login?expired=1&from=${encodeURIComponent(currentPath)}`;
      throw new ApiError("Session expired. Redirecting to login...", 401);
    }
  }

  let data: unknown;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMessage =
      (data as { detail?: string; message?: string })?.detail ||
      (data as { detail?: string; message?: string })?.message ||
      `Request failed with status ${response.status}`;

    throw new ApiError(errorMessage, response.status, data);
  }

  return data as T;
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestInit) =>
    apiFetch<T>(endpoint, { ...options, method: "GET" }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    apiFetch<T>(endpoint, {
      ...options,
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),

  patch: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    apiFetch<T>(endpoint, {
      ...options,
      method: "PATCH",
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),

  delete: <T>(endpoint: string, options?: RequestInit) =>
    apiFetch<T>(endpoint, { ...options, method: "DELETE" }),

  download: async (endpoint: string, defaultFilename: string = "export.csv") => {
    const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    const url = `/api/proxy${path}`;
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) {
      throw new ApiError(`Download failed with status ${res.status}`, res.status);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("content-disposition");
    let filename = defaultFilename;
    if (disposition && disposition.includes("filename=")) {
      const match = disposition.match(/filename="?([^";]+)"?/);
      if (match && match[1]) filename = match[1];
    }
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(blobUrl);
  },
};
