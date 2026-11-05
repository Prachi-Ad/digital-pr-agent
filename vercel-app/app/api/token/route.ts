import { createHmac } from "node:crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TOKEN_TTL_SECONDS = 300;
const TOKEN_WINDOW_MS = 10 * 60 * 1000;
const TOKEN_LIMIT_PER_WINDOW = 40;

// Only these browser origins may mint a demo token. Preview deployments of
// this Vercel team are allowed so preview work keeps functioning.
const EXACT_HOSTS = new Set([
  "pr.prachiadmane.com",
  "vercel-app-gules-three.vercel.app",
  "vercel-app-prachi-8a13.vercel.app",
  "vercel-app-git-main-prachi-8a13.vercel.app",
  "localhost:3000",
  "127.0.0.1:3000",
]);

type Bucket = { count: number; resetAt: number };
const buckets = new Map<string, Bucket>();

function hostOf(value: string | null): string {
  if (!value) return "";
  try {
    return new URL(value).host.toLowerCase();
  } catch {
    return "";
  }
}

function hostAllowed(host: string): boolean {
  if (!host) return false;
  if (EXACT_HOSTS.has(host)) return true;
  return host.endsWith(".vercel.app") && host.includes("prachi-8a13");
}

function clientIp(req: Request): string {
  const realIp = (req.headers.get("x-real-ip") || "").trim();
  if (realIp) return realIp;
  const forwarded = (req.headers.get("x-forwarded-for") || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return forwarded.length > 0 ? forwarded[forwarded.length - 1] : "unknown";
}

function allowToken(ip: string): boolean {
  const now = Date.now();
  if (buckets.size > 5000) {
    for (const [key, bucket] of buckets) {
      if (bucket.resetAt <= now) buckets.delete(key);
    }
  }
  const bucket = buckets.get(ip);
  if (!bucket || bucket.resetAt <= now) {
    buckets.set(ip, { count: 1, resetAt: now + TOKEN_WINDOW_MS });
    return true;
  }
  if (bucket.count >= TOKEN_LIMIT_PER_WINDOW) return false;
  bucket.count += 1;
  return true;
}

function sign(exp: number, secret: string): string {
  return createHmac("sha256", secret).update(`v1.${exp}`).digest("base64url");
}

export async function POST(req: Request) {
  const secret = process.env.DEMO_SIGNING_SECRET || "";
  if (secret.length < 32) {
    return Response.json(
      { detail: "The demo is not configured for requests right now." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  const origin = req.headers.get("origin") || req.headers.get("referer");
  if (!hostAllowed(hostOf(origin))) {
    return Response.json(
      { detail: "This endpoint is only available from the demo site." },
      { status: 403, headers: { "Cache-Control": "no-store" } }
    );
  }

  const ip = clientIp(req);
  if (!allowToken(ip)) {
    return Response.json(
      { detail: "Too many sessions started. Please wait a few minutes and reload." },
      { status: 429, headers: { "Cache-Control": "no-store", "Retry-After": "600" } }
    );
  }

  const exp = Math.floor(Date.now() / 1000) + TOKEN_TTL_SECONDS;
  return Response.json(
    { token: `v1.${exp}.${sign(exp, secret)}`, expiresIn: TOKEN_TTL_SECONDS },
    { status: 200, headers: { "Cache-Control": "no-store" } }
  );
}
