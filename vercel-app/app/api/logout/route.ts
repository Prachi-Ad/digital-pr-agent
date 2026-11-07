import { clearedAuthCookieHeader } from "@/app/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  return Response.json(
    { ok: true },
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        "Set-Cookie": clearedAuthCookieHeader(),
      },
    }
  );
}
