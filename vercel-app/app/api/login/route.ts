import { timingSafeEqual } from "node:crypto";
import { authCookieHeader, sitePassword } from "@/app/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_ATTEMPTS = 10;
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PASSWORD_LENGTH = 256;

type Bucket = { count: number; failures: number; resetAt: number };
const buckets = new Map<string, Bucket>();

function clientIp(req: Request): string {
  const realIp = (req.headers.get("x-real-ip") || "").trim();
  if (realIp) return realIp;
  const forwarded = (req.headers.get("x-forwarded-for") || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return forwarded.length > 0 ? forwarded[forwarded.length - 1] : "unknown";
}

function failureAllowed(ip: string): boolean {
  const now = Date.now();
  if (buckets.size > 5000) {
    for (const [key, bucket] of buckets) {
      if (bucket.resetAt <= now) buckets.delete(key);
    }
  }
  const bucket = buckets.get(ip);
  if (!bucket || bucket.resetAt <= now) {
    buckets.set(ip, { count: 1, failures: 0, resetAt: now + WINDOW_MS });
    return true;
  }
  return bucket.failures < MAX_ATTEMPTS;
}

function recordFailure(ip: string) {
  const bucket = buckets.get(ip);
  if (bucket) bucket.failures += 1;
}

function passwordsMatch(provided: string, expected: string): boolean {
  const a = Buffer.from(`v1:${provided}`, "utf8");
  const b = Buffer.from(`v1:${expected}`, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(req: Request) {
  const configured = sitePassword();
  if (!configured) {
    return Response.json(
      { detail: "Sign-in is not configured yet." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }
  let password = "";
  try {
    const body = await req.json();
    password = String(body?.password || "").slice(0, MAX_PASSWORD_LENGTH + 1);
  } catch {
    password = "";
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return Response.json(
      { detail: "Wrong password. Try again." },
      { status: 401, headers: { "Cache-Control": "no-store" } }
    );
  }
  const ip = clientIp(req);
  if (!failureAllowed(ip)) {
    return Response.json(
      { detail: "Too many sign-in attempts. Wait a few minutes and try again." },
      { status: 429, headers: { "Cache-Control": "no-store", "Retry-After": "600" } }
    );
  }
  if (!password || !passwordsMatch(password, configured)) {
    // Same message for missing/wrong to avoid username-style enumeration.
    // A short delay makes brute force slightly more expensive.
    recordFailure(ip);
    await new Promise((r) => setTimeout(r, 400));
    return Response.json(
      { detail: "Wrong password. Try again." },
      { status: 401, headers: { "Cache-Control": "no-store" } }
    );
  }
  return Response.json(
    { ok: true },
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        "Set-Cookie": authCookieHeader(),
      },
    }
  );
}
