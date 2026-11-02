/**
 * Edge-compatible cryptographic session verification using Web Crypto API.
 * Works seamlessly in Next.js Middleware Edge Runtime without Node.js dependencies.
 */

export interface EdgeSessionData {
  sub: string;
  role: "admin";
  csrf: string;
  iat: number;
  exp: number;
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

export async function verifySessionEdge(
  token: string | undefined | null,
  secretStr: string
): Promise<EdgeSessionData | null> {
  if (!token || typeof token !== "string") return null;

  const parts = token.split(".");
  if (parts.length !== 2) return null;

  const [payloadStr, signatureHex] = parts;

  try {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(secretStr);
    const dataToSign = encoder.encode(payloadStr);

    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      keyData,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"]
    );

    const sigBytes = hexToBytes(signatureHex);
    const isValid = await crypto.subtle.verify("HMAC", cryptoKey, sigBytes as BufferSource, dataToSign);

    if (!isValid) return null;

    // Decode base64url payload
    const base64 = payloadStr.replace(/-/g, "+").replace(/_/g, "/");
    const jsonStr = atob(base64);
    const payload: EdgeSessionData = JSON.parse(jsonStr);

    const now = Math.floor(Date.now() / 1000);
    if (payload.exp < now) {
      return null;
    }

    return payload;
  } catch {
    return null;
  }
}
