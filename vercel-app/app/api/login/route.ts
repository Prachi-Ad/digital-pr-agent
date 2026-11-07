import { timingSafeEqual } from "node:crypto";
import { authCookieHeader, sitePassword } from "@/app/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
    password = String(body?.password || "");
  } catch {
    password = "";
  }
  if (!password || !passwordsMatch(password, configured)) {
    // Same message for missing/wrong to avoid username-style enumeration.
    // A short delay makes brute force slightly more expensive.
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
