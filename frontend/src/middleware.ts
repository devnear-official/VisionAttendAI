import { NextRequest, NextResponse } from "next/server";
import { verifySessionEdge } from "@/lib/auth/edge-verify";

const COOKIE_NAME = process.env.COOKIE_NAME || "va_session";
const SESSION_SECRET = process.env.SESSION_SECRET || "fallback_dev_secret_key_needs_32_chars_at_least";

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Public paths that do not require authentication
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon.ico") ||
    pathname.endsWith(".png") ||
    pathname.endsWith(".svg") ||
    pathname.endsWith(".jpg")
  ) {
    // If user is already authenticated and visits /login, redirect to /dashboard
    if (pathname === "/login") {
      const token = req.cookies.get(COOKIE_NAME)?.value;
      const session = await verifySessionEdge(token, SESSION_SECRET);
      if (session) {
        return NextResponse.redirect(new URL("/dashboard", req.url));
      }
    }
    return NextResponse.next();
  }

  // Check session cookie
  const token = req.cookies.get(COOKIE_NAME)?.value;
  const session = await verifySessionEdge(token, SESSION_SECRET);

  if (!session) {
    // If accessing an API route, return 401 instead of redirecting
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: "Unauthorized. Session expired or invalid." },
        { status: 401 }
      );
    }

    const loginUrl = new URL("/login", req.url);
    if (pathname !== "/" && pathname !== "/dashboard") {
      loginUrl.searchParams.set("from", pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  // Redirect root path / to /dashboard
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
