import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, CSRF_COOKIE_NAME, createSessionToken } from "@/lib/auth/session";

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || "dev_admin_secret_key_change_in_production";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { apiKey } = body;

    if (!apiKey || typeof apiKey !== "string") {
      return NextResponse.json(
        { error: "Admin API Key is required" },
        { status: 400 }
      );
    }

    // Verify against backend server or compare with ADMIN_API_KEY directly
    let isValid = false;
    if (apiKey === ADMIN_API_KEY) {
      isValid = true;
    } else {
      // Test the key against backend students endpoint
      try {
        const verifyRes = await fetch(`${BACKEND_INTERNAL_URL}/api/v1/students?limit=1`, {
          headers: {
            Authorization: `Bearer ${apiKey}`,
          },
        });
        isValid = verifyRes.status === 200;
      } catch {
        isValid = false;
      }
    }

    if (!isValid) {
      return NextResponse.json(
        { error: "Invalid Administrative Master Token" },
        { status: 401 }
      );
    }

    const { token, csrfToken, expiresAt } = createSessionToken("superadmin");
    const isProduction = process.env.NODE_ENV === "production";

    const response = NextResponse.json({
      status: "authenticated",
      user: {
        role: "admin",
        name: "Institutional Administrator",
        email: "admin@visionattend.university.edu",
      },
      expiresAt: expiresAt.toISOString(),
    });

    // 1. httpOnly Session Cookie (Never accessible by browser JavaScript)
    response.cookies.set({
      name: COOKIE_NAME,
      value: token,
      httpOnly: true,
      secure: isProduction,
      sameSite: "lax",
      expires: expiresAt,
      path: "/",
    });

    // 2. Client-readable CSRF Token Cookie (used for double-submit / CSRF header verification)
    response.cookies.set({
      name: CSRF_COOKIE_NAME,
      value: csrfToken,
      httpOnly: false,
      secure: isProduction,
      sameSite: "lax",
      expires: expiresAt,
      path: "/",
    });

    return response;
  } catch {
    return NextResponse.json(
      { error: "Internal authentication error" },
      { status: 500 }
    );
  }
}
