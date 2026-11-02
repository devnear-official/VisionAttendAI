import crypto from "crypto";

const isProduction = process.env.NODE_ENV === "production";
const RAW_SECRET = process.env.SESSION_SECRET;

if (isProduction && (!RAW_SECRET || RAW_SECRET.length < 32)) {
  throw new Error("SECURITY FAULT: SESSION_SECRET must be configured with at least 32 characters in production.");
}

const SESSION_SECRET = RAW_SECRET || "visionattend_local_dev_hmac_secret_key_9876543210123456";
const SESSION_MAX_AGE_SECONDS = parseInt(process.env.SESSION_MAX_AGE_SECONDS || "86400", 10);
export const COOKIE_NAME = process.env.COOKIE_NAME || "va_session";
export const CSRF_COOKIE_NAME = "va_csrf";

export interface SessionData {
  sub: string;
  role: "admin";
  csrf: string;
  iat: number;
  exp: number;
}

/**
 * Creates a signed, tamper-proof session token.
 */
export function createSessionToken(sub: string = "superadmin"): { token: string; csrfToken: string; expiresAt: Date } {
  const iat = Math.floor(Date.now() / 1000);
  const exp = iat + SESSION_MAX_AGE_SECONDS;
  const csrf = crypto.randomBytes(24).toString("hex");

  const payload: SessionData = {
    sub,
    role: "admin",
    csrf,
    iat,
    exp,
  };

  const payloadStr = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = crypto
    .createHmac("sha256", SESSION_SECRET)
    .update(payloadStr)
    .digest("hex");

  const token = `${payloadStr}.${signature}`;
  const expiresAt = new Date(exp * 1000);

  return { token, csrfToken: csrf, expiresAt };
}

/**
 * Verifies the cryptographic HMAC signature and expiration of a session token.
 */
export function verifySessionToken(token: string | undefined | null): SessionData | null {
  if (!token || typeof token !== "string") return null;

  const parts = token.split(".");
  if (parts.length !== 2) return null;

  const [payloadStr, signature] = parts;

  try {
    const expectedSig = crypto
      .createHmac("sha256", SESSION_SECRET)
      .update(payloadStr)
      .digest("hex");

    // Constant-time comparison prevents timing attacks
    const sigBuffer = Buffer.from(signature, "hex");
    const expectedBuffer = Buffer.from(expectedSig, "hex");

    if (sigBuffer.length !== expectedBuffer.length) return null;
    if (!crypto.timingSafeEqual(sigBuffer, expectedBuffer)) return null;

    const payloadJson = Buffer.from(payloadStr, "base64url").toString("utf8");
    const payload: SessionData = JSON.parse(payloadJson);

    // Validate expiration
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp < now) {
      return null;
    }

    return payload;
  } catch {
    return null;
  }
}
