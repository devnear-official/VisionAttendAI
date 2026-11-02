import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, verifySessionToken } from "@/lib/auth/session";

export async function GET(req: NextRequest) {
  const sessionCookie = req.cookies.get(COOKIE_NAME)?.value;
  const session = verifySessionToken(sessionCookie);

  if (!session) {
    return NextResponse.json(
      { authenticated: false },
      { status: 401 }
    );
  }

  return NextResponse.json({
    authenticated: true,
    user: {
      id: session.sub,
      role: session.role,
      name: "Institutional Administrator",
      email: "admin@visionattend.university.edu",
    },
    expiresAt: new Date(session.exp * 1000).toISOString(),
  });
}
