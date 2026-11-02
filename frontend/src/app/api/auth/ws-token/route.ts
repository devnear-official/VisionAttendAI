import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, verifySessionToken } from "@/lib/auth/session";

export async function GET(req: NextRequest) {
  const sessionCookie = req.cookies.get(COOKIE_NAME)?.value;
  const session = verifySessionToken(sessionCookie);

  if (!session || !sessionCookie) {
    return NextResponse.json(
      { error: "Unauthorized session." },
      { status: 401 }
    );
  }

  return NextResponse.json({
    token: sessionCookie,
  });
}
