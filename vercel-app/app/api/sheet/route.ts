import { google } from "googleapis";
import { isAuthenticated } from "@/app/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TAB = (process.env.SHEET_TAB || "Pitches").trim() || "Pitches";
// A: key (oppUrl##name) — used to update the same pitch instead of duplicating.
const HEADERS = [
  "key", "date", "angle", "publication", "site_domain", "article_title", "article_url",
  "used", "pr_fit", "pr_score", "contact_name", "contact_role", "email",
  "subject", "body", "status", "coverage_url",
];

function serviceAccount(): any {
  const raw = (process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "").trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function sheets() {
  const creds = serviceAccount();
  const sheetId = (process.env.SHEET_ID || "").trim();
  if (!creds || !sheetId) return null;
  const auth = new google.auth.JWT({
    email: creds.client_email,
    key: creds.private_key,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
  return { api: google.sheets({ version: "v4", auth }), sheetId };
}

async function ensureTab(api: any, sheetId: string) {
  const meta = await api.spreadsheets.get({ spreadsheetId: sheetId });
  const titles = (meta.data.sheets || []).map((s: any) => s.properties?.title);
  if (!titles.includes(TAB)) {
    await api.spreadsheets.batchUpdate({
      spreadsheetId: sheetId,
      requestBody: { requests: [{ addSheet: { properties: { title: TAB } } }] },
    });
    await api.spreadsheets.values.update({
      spreadsheetId: sheetId,
      range: `${TAB}!A1:${String.fromCharCode(64 + HEADERS.length)}1`,
      valueInputOption: "RAW",
      requestBody: { values: [HEADERS] },
    });
  }
}

export async function GET() {
  const client = await sheets();
  return Response.json(
    {
      configured: !!client,
      tab: TAB,
      columns: HEADERS.filter((h) => h !== "key"),
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}

export async function POST(req: Request) {
  if (!isAuthenticated(req.headers.get("cookie"))) {
    return Response.json({ detail: "Sign in required." }, { status: 401 });
  }
  const client = await sheets();
  if (!client) {
    return Response.json(
      { detail: "Google Sheet is not connected. Set SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON in Vercel." },
      { status: 503 }
    );
  }
  let rows: any[][] = [];
  try {
    const body = await req.json();
    rows = Array.isArray(body?.rows) ? body.rows : [];
  } catch {
    rows = [];
  }
  rows = rows.filter((r) => Array.isArray(r) && r.length === HEADERS.length);
  if (rows.length === 0) {
    return Response.json({ detail: "No rows to sync." }, { status: 400 });
  }
  if (rows.length > 200) {
    return Response.json({ detail: "Max 200 rows per sync." }, { status: 400 });
  }

  const { api, sheetId } = client;
  try {
    await ensureTab(api, sheetId);
    const existing = await api.spreadsheets.values.get({
      spreadsheetId: sheetId,
      range: `${TAB}!A2:A10000`,
    });
    const keys: string[] = (existing.data.values || []).map((r: any[]) => String(r[0] || ""));
    let updated = 0;
    let appended = 0;
    const toAppend: any[][] = [];
    const updates: Array<{ range: string; values: any[][] }> = [];
    const seen = new Set<string>();
    for (const row of rows) {
      const key = String(row[0] || "");
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const idx = keys.indexOf(key);
      if (idx >= 0) {
        updates.push({ range: `${TAB}!A${idx + 2}`, values: [row] });
        updated += 1;
      } else {
        toAppend.push(row);
        keys.push(key);
        appended += 1;
      }
    }
    if (updates.length) {
      await api.spreadsheets.values.batchUpdate({
        spreadsheetId: sheetId,
        requestBody: { valueInputOption: "RAW", data: updates },
      });
    }
    if (toAppend.length) {
      await api.spreadsheets.values.append({
        spreadsheetId: sheetId,
        range: `${TAB}!A1`,
        valueInputOption: "RAW",
        insertDataOption: "INSERT_ROWS",
        requestBody: { values: toAppend },
      });
    }
    return Response.json({ ok: true, updated, appended }, { status: 200 });
  } catch (err: any) {
    const msg = String(err?.message || err);
    const detail = msg.includes("Unable to parse range") || msg.includes("Requested entity was not found")
      ? "Cannot open the sheet. Check SHEET_ID and that the service account has Editor access."
      : `Sheet sync failed: ${msg.slice(0, 300)}`;
    return Response.json({ detail }, { status: 502 });
  }
}
