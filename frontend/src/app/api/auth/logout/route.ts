import { NextResponse } from "next/server";
import { COOKIE_NAME, CSRF_COOKIE_NAME } from "@/lib/auth/session";

export async function POST() {
  const response = NextResponse.json({
    status: "logged_out",
    message: "Administrative session successfully terminated.",
  });

  const isProduction = process.env.NODE_ENV === "production";

  // Completely wipe session cookie
  response.cookies.set({
    name: COOKIE_NAME,
    value: "",
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    expires: new Date(0),
    maxAge: 0,
    path: "/",
  });

  // Completely wipe CSRF token cookie
  response.cookies.set({
    name: CSRF_COOKIE_NAME,
    value: "",
    httpOnly: false,
    secure: isProduction,
    sameSite: "lax",
    expires: new Date(0),
    maxAge: 0,
    path: "/",
  });

  return response;
}
