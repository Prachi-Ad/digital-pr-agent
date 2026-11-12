import { google } from "googleapis";
import { isAuthenticated } from "@/app/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TAB = (process.env.SHEET_TAB || "Pitches").trim() || "Pitches";
// A: key (oppUrl##name) — used to update the same pitch instead of duplicating.
const HEADER_MAP: Record<string, string[]> = {
  Pitches: [
    "key", "date", "angle", "publication", "site_domain", "article_title", "article_url",
    "used", "pr_fit", "pr_score", "contact_name", "contact_role", "email",
    "subject", "body", "status", "coverage_url",
  ],
  Contacts: [
    "key", "name", "publication", "role", "beat", "email", "contact_page",
    "profile_url", "source_article", "source_url", "last_angle", "last_seen", "status",
  ],
  Coverage: [
    "key", "date", "contact_name", "publication", "article_title", "article_url",
    "subject", "coverage_url", "status",
  ],
  Listicles: [
    "key", "date", "publication", "listicle_title", "listicle_url", "placement_type",
    "contact_name", "contact_role", "email", "subject", "body", "status", "coverage_url",
  ],
};
const HEADERS = HEADER_MAP.Pitches;

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

async function ensureTab(api: any, sheetId: string, tab: string, headers: string[]) {
  const meta = await api.spreadsheets.get({ spreadsheetId: sheetId });
  const titles = (meta.data.sheets || []).map((s: any) => s.properties?.title);
  if (!titles.includes(tab)) {
    await api.spreadsheets.batchUpdate({
      spreadsheetId: sheetId,
      requestBody: { requests: [{ addSheet: { properties: { title: tab } } }] },
    });
    await api.spreadsheets.values.update({
      spreadsheetId: sheetId,
      range: `${tab}!A1:${String.fromCharCode(64 + headers.length)}1`,
      valueInputOption: "RAW",
      requestBody: { values: [headers] },
    });
  }
}

export async function GET(request: Request) {
  const webhook = (process.env.SHEET_WEBHOOK_URL || "").trim();
  const client = webhook ? null : await sheets();
  const probe = new URL(request.url).searchParams.get("probe") === "1";
  const headers = { "Cache-Control": "no-store" };

  let reachable: boolean | null = null;
  let probeStatus: number | null = null;
  let probeError = "";
  if (probe) {
    if (!webhook) {
      probeError = "No webhook URL is configured for this deployment.";
    } else {
      // Env vars only prove a URL exists. This asks the deployment whether it
      // answers at all, which is what "connected" is supposed to mean.
      try {
        const res = await fetch(webhook, {
          method: "GET",
          redirect: "manual",
          cache: "no-store",
          signal: AbortSignal.timeout(8000),
        });
        probeStatus = res.status;
        reachable = res.status < 400;
      } catch (err: any) {
        reachable = false;
        probeError = String(err?.message || err).slice(0, 200);
      }
    }
  }

  return Response.json(
    {
      configured: !!webhook || !!client,
      mode: webhook ? "webhook" : "service-account",
      tab: TAB,
      columns: HEADERS.filter((h) => h !== "key"),
      ...(probe ? { reachable, probeStatus, probeError } : {}),
    },
    { headers }
  );
}

async function syncViaWebhook(tab: string, rows: any[][]) {
  const url = (process.env.SHEET_WEBHOOK_URL || "").trim();
  const token = (process.env.SHEET_WEBHOOK_TOKEN || "").trim();
  if (!url || !token) return null;
  const headers = HEADER_MAP[tab];
  const payload = rows.map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ""])));
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, tab, rows: payload }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `Webhook sync failed (${res.status}).`);
  return data;
}

export async function POST(req: Request) {
  if (!isAuthenticated(req.headers.get("cookie"))) {
    return Response.json({ detail: "Sign in required." }, { status: 401 });
  }
  let rows: any[][] = [];
  let tab = TAB;
  try {
    const body = await req.json();
    rows = Array.isArray(body?.rows) ? body.rows : [];
    if (typeof body?.tab === "string" && HEADER_MAP[body.tab]) tab = body.tab;
  } catch {
    rows = [];
  }
  const headers = HEADER_MAP[tab];
  rows = rows.filter((r) => Array.isArray(r) && r.length === headers.length);
  if (rows.length === 0) {
    return Response.json({ detail: "No rows to sync." }, { status: 400 });
  }
  if (rows.length > 200) {
    return Response.json({ detail: "Max 200 rows per sync." }, { status: 400 });
  }

  // Key-free path: Apps Script webhook (works where key creation is blocked).
  if ((process.env.SHEET_WEBHOOK_URL || "").trim()) {
    try {
      const data = await syncViaWebhook(tab, rows);
      if (!data) throw new Error("Webhook not configured.");
      return Response.json(
        { ok: true, tab, updated: data.updated || 0, appended: data.appended || 0 },
        { status: 200 }
      );
    } catch (err: any) {
      return Response.json(
        { detail: String(err?.message || err).slice(0, 300) },
        { status: 502 }
      );
    }
  }

  const client = await sheets();
  if (!client) {
    return Response.json(
      { detail: "Google Sheet is not connected. Set SHEET_WEBHOOK_URL + SHEET_WEBHOOK_TOKEN, or SHEET_ID + GOOGLE_SERVICE_ACCOUNT_JSON in Vercel." },
      { status: 503 }
    );
  }

  const { api, sheetId } = client;
  try {
    await ensureTab(api, sheetId, tab, headers);
    const existing = await api.spreadsheets.values.get({
      spreadsheetId: sheetId,
      range: `${tab}!A2:A10000`,
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
        updates.push({ range: `${tab}!A${idx + 2}`, values: [row] });
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
        range: `${tab}!A1`,
        valueInputOption: "RAW",
        insertDataOption: "INSERT_ROWS",
        requestBody: { values: toAppend },
      });
    }
    return Response.json({ ok: true, tab, updated, appended }, { status: 200 });
  } catch (err: any) {
    const msg = String(err?.message || err);
    const detail = msg.includes("Unable to parse range") || msg.includes("Requested entity was not found")
      ? "Cannot open the sheet. Check SHEET_ID and that the service account has Editor access."
      : `Sheet sync failed: ${msg.slice(0, 300)}`;
    return Response.json({ detail }, { status: 502 });
  }
}
