import { createHmac, timingSafeEqual } from "node:crypto";

export const AUTH_COOKIE = "pr_auth";
const AUTH_MESSAGE = "vista-pr-auth-v1";

export function sitePassword(): string {
  return (process.env.SITE_PASSWORD || "").trim();
}

export function expectedAuthValue(): string {
  const password = sitePassword();
  if (!password) return "";
  return createHmac("sha256", password).update(AUTH_MESSAGE).digest("base64url");
}

export function isAuthenticated(cookieHeader: string | null): boolean {
  const expected = expectedAuthValue();
  if (!expected) return false;
  const cookies = parseCookies(cookieHeader);
  const provided = (cookies[AUTH_COOKIE] || "").trim();
  if (!provided) return false;
  try {
    const a = Buffer.from(provided, "utf8");
    const b = Buffer.from(expected, "utf8");
    return a.length === b.length && timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

export function parseCookies(cookieHeader: string | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!cookieHeader) return out;
  for (const part of cookieHeader.split(";")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const name = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (name && !(name in out)) {
      try {
        out[name] = decodeURIComponent(value);
      } catch {
        out[name] = value;
      }
    }
  }
  return out;
}

export function authCookieHeader(): string {
  const value = expectedAuthValue();
  // 1-year persistent login; Secure is added automatically by browsers on HTTPS
  // when the attribute is present. Vercel serves HTTPS, local dev is HTTP.
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${AUTH_COOKIE}=${encodeURIComponent(value)}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax${secure}`;
}

export function clearedAuthCookieHeader(): string {
  return `${AUTH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`;
}
