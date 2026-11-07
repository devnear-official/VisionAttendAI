import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, verifySessionToken } from "@/lib/auth/session";

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || "dev_admin_secret_key_change_in_production";

interface RouteRule {
  pattern: RegExp;
  methods: string[];
}

/**
 * Strict whitelist of allowed backend routes and permissible HTTP methods.
 * Any request attempting path traversal or calling unsanctioned endpoints will be blocked.
 */
const ALLOWED_ROUTES: RouteRule[] = [
  // Health diagnostics
  { pattern: /^v1\/health$/, methods: ["GET"] },
  // Student directory & profile
  { pattern: /^v1\/students$/, methods: ["GET", "POST"] },
  { pattern: /^v1\/students\/[a-zA-Z0-9_-]+$/, methods: ["GET", "PATCH", "DELETE"] },
  // Biometric face enrollment & template management
  { pattern: /^v1\/face\/enroll$/, methods: ["POST"] },
  { pattern: /^v1\/face\/enroll\/session(\/[a-zA-Z0-9_-]+)?$/, methods: ["GET", "POST", "DELETE"] },
  { pattern: /^v1\/face\/person\/[a-zA-Z0-9_-]+$/, methods: ["GET", "DELETE"] },
  // Attendance ledger & check-ins
  { pattern: /^v1\/attendance(\/[a-zA-Z0-9_-]+)?$/, methods: ["GET", "DELETE"] },
  // Analytics & summaries
  { pattern: /^v1\/analytics(\/[a-zA-Z0-9_-]+)?$/, methods: ["GET"] },
  // Edge camera devices & telemetry
  { pattern: /^v1\/devices$/, methods: ["GET", "POST"] },
  { pattern: /^v1\/devices\/heartbeat$/, methods: ["POST"] },
  { pattern: /^v1\/devices\/[a-zA-Z0-9_-]+(\/(rotate-key|speaker|speak))?$/, methods: ["GET", "POST", "PATCH", "DELETE"] },
];

async function proxyHandler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  // 1. Session verification (server-side cryptographic check)
  const sessionCookie = req.cookies.get(COOKIE_NAME)?.value;
  const session = verifySessionToken(sessionCookie);

  if (!session) {
    return NextResponse.json(
      { error: "Unauthorized session. Please authenticate as administrator." },
      { status: 401 }
    );
  }

  // 2. CSRF verification on mutating methods
  const method = req.method.toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfHeader = req.headers.get("x-csrf-token");
    if (!csrfHeader || csrfHeader !== session.csrf) {
      return NextResponse.json(
        { error: "CSRF token validation failed." },
        { status: 403 }
      );
    }
  }

  // 3. Path sanitization and traversal prevention
  const { path } = await params;
  for (const segment of path) {
    if (segment.includes("..") || segment.includes("\\") || segment.includes("//")) {
      return NextResponse.json(
        { error: "Security violation: Invalid path segment." },
        { status: 400 }
      );
    }
  }

  const targetPath = path.join("/");

  // 4. Route and HTTP method whitelist enforcement
  const isAllowed = ALLOWED_ROUTES.some(
    (rule) => rule.pattern.test(targetPath) && rule.methods.includes(method)
  );

  if (!isAllowed) {
    return NextResponse.json(
      { error: `Forbidden: Route '${targetPath}' with method '${method}' is not permitted by BFF policy.` },
      { status: 403 }
    );
  }

  // 5. Construct URL & forward headers with injected server-side secret
  const searchParams = req.nextUrl.search;
  const targetUrl = `${BACKEND_INTERNAL_URL}/api/${targetPath}${searchParams}`;

  const forwardHeaders = new Headers();
  forwardHeaders.set("Authorization", `Bearer ${ADMIN_API_KEY}`);

  const clientContentType = req.headers.get("content-type");
  if (clientContentType) {
    forwardHeaders.set("content-type", clientContentType);
  }

  // 6. Forward body if present
  let body: BodyInit | undefined = undefined;
  if (["POST", "PUT", "PATCH"].includes(method)) {
    if (clientContentType?.includes("multipart/form-data")) {
      body = await req.arrayBuffer();
    } else {
      body = await req.text();
    }
  }

  try {
    const backendResponse = await fetch(targetUrl, {
      method,
      headers: forwardHeaders,
      body,
    });

    const responseData = await backendResponse.arrayBuffer();

    const responseHeaders = new Headers();
    const respContentType = backendResponse.headers.get("content-type");
    if (respContentType) {
      responseHeaders.set("content-type", respContentType);
    }

    return new NextResponse(responseData, {
      status: backendResponse.status,
      statusText: backendResponse.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Backend communication error",
        detail: error instanceof Error ? error.message : "Unknown error connecting to backend service",
      },
      { status: 502 }
    );
  }
}

export const GET = proxyHandler;
export const POST = proxyHandler;
export const PATCH = proxyHandler;
export const PUT = proxyHandler;
export const DELETE = proxyHandler;
