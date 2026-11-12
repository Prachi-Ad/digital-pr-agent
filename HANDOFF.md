# Handoff — Digital PR Research Agent

Last updated: 2026-11-12
Live: https://pr.prachiadmane.com (Vercel, Next.js 14.2.35 + Python API)
Repo: https://github.com/Prachi-Ad/digital-pr-agent (branch `main`)
Local path: `C:\Users\Prachi\vista-pr-agent`

---

## 1. What this is

A research-only Digital PR tool for Vista Social. It turns a published article (yours
or a publisher's) into pitch angles, finds publisher articles worth pitching, writes a
pitch to that publication's editorial team, and logs everything to Google Sheets.
**It never sends email and never submits forms.** The local Streamlit app is the legacy
full tool; the Vercel app is the primary one.

**No people research.** This build does not look for writers, editors, contacts, or email
addresses. There is no media library and no Contacts tab. Drafts are addressed to the
publication's editorial team; the model is told never to invent a recipient. The one
exception is the sheet's legacy `contact_name`/`email` columns, which stay empty so old
rows and existing spreadsheets keep working.

**Single user.** This deployment is used by one person (Prachi). It is not a multi-tenant
product. That is the intended design, not a stopgap: the shared password gate is the
access model, there are no accounts, and per-browser state is owner state.

**No email surface.** This app has no send button, no credentials, no opt-out list, no
send log, and no mention of sending email as a feature in Settings. Those belong to the
legacy local Streamlit app and stay out of this build. Contact *lookup* (finding a
publicly published address) is research and stays.

## 2. Live surface

| Area | Path | Notes |
| --- | --- | --- |
| Sign-in | `/login` | Shared password gate, signed `pr_auth` cookie |
| App | `/` | Workspace → Research Library → Settings |
| Sheet sync | `/api/sheet` | Apps Script webhook; upsert by key. Manual only — nothing is written unless a Sync button is pressed. `POST {action:"clear", tab}` deletes data rows in one tab. `GET ?probe=1` checks that the deployment answers (it does not test the token). |
| Token | `/api/token` | Short-lived HMAC for the Python API |
| Model API | `/api/analyze` | `action`-based; also `GET` = health + budget |
| LLM/markdown | `/llm`, `/llms.txt`, `/skills/seo-aeo-digital-pr.md` | Public, no login |
| robots | `/robots.txt` | Allows AI crawlers |

## 3. Architecture

```
Browser (Next.js app/page.tsx, 4k lines)
  ├─ cookie gate (middleware.ts + app/lib/auth.ts)
  ├─ fetch /api/token  → bearer token (HMAC, 5 min)
  ├─ fetch /api/analyze (Python FastAPI, api/analyze.py)
  │     └─ api/_security.py   auth, origin, rate limits, daily budget
  │     └─ agent.py           OpenAI Agents SDK; one shared event loop
  │     └─ api/dr.py          Ahrefs free Domain Rating
  └─ fetch /api/sheet     → Apps Script webhook → Google Sheet
```

Python API actions: `analyze`, `own-pages`, `domain-scan`, `opportunities`, `draft`,
`listicles`, `listicle-draft`, `publisher-policy`, `site-metrics`. Removed with the
people layer: `journalists`, `person-contact`, `collect-writers`, `listicle-contact`.

## 4. Environment (Vercel → Project `vercel-app`, team `prachi-8a13`)

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Model + web search |
| `DEMO_SIGNING_SECRET` | HMAC for `/api/token` (≥32 chars, fails closed) |
| `SITE_PASSWORD` | Shared sign-in password (gate + cookie HMAC) |
| `BRAND_NAME`, `BRAND_DOMAIN`, `PRODUCT_DESCRIPTION` | Brand config; `BRAND_DOMAIN` drives own-site rules |
| `SHEET_WEBHOOK_URL`, `SHEET_WEBHOOK_TOKEN` | Apps Script sync |
| `AHREFS_API_KEY` | Free DR endpoint |
| `DEMO_CLIENT_REQUESTS_PER_DAY` | 150 (per browser) |
| `DEMO_IP_REQUESTS_PER_DAY` | 300 |
| `DEMO_IP_REQUESTS_PER_10_MIN` | 30 |
| `DEMO_DAILY_REQUEST_CAP` | 800 (per instance) |
| `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` | Optional. Shared budget counter (Upstash REST; `KV_REST_API_URL`/`KV_REST_API_TOKEN` also work). Without them the caps are per-instance memory. |

Changing any env var requires a redeploy (Vercel bakes them at build time).

## 5. Deploy

```powershell
cd C:\Users\Prachi\vista-pr-agent
npm --prefix vercel-app run build          # optional local check
git add -A; git commit -m "…"; git push origin main
```
GitHub push → Vercel builds the `vercel-app` root directory → aliases
`pr.prachiadmane.com`. Never run `vercel --prod` from the repo root (it creates a
stray Python project).

## 6. Tests

```powershell
C:\Users\Prachi\vista-pr-agent\.venv\Scripts\python.exe -m unittest discover -s vercel-app/tests -v
```
48 tests in three files:

- `test_safety.py` (25): URL/email sanitising, blog-only filter, email rules, precheck,
  dedupe.
- `test_guards.py` (15): auth cookie, origin allowlist, token shape/expiry/forgery, body
  cap, fail-closed secret, and the budget rules — a refused request charges nothing, the
  10-minute window and the daily ceiling are reported separately, and exhausting one
  limit does not burn the others.
- `test_shared_budget.py` (8): runs a fake Upstash REST endpoint and proves a cold start
  does not reset the shared count, the ceiling is enforced on the shared number, refusals
  do not charge, and an unreachable store fails closed.

PowerShell prints unit-test progress on stderr, so a piped run can look like it failed;
trust the printed `OK` and an unpiped exit code.


## 7. Google Sheet

Tabs: **Dashboard**, **Pitches**, **Listicles**, **Coverage**. One spreadsheet, always the
same one: the app only ever POSTs to the single `SHEET_WEBHOOK_URL`, the Apps Script is
bound to that document, and rows upsert by their `key` so a re-sync refreshes a row instead
of adding a duplicate. Nothing creates a spreadsheet or a tab per batch. (A legacy
**Contacts** tab may still exist in the document; the app no longer writes to it.)

Styling lives in the script: ink header band (`#16122c`) with paper text (`#faf8f1`),
Inter, bold, frozen header and key column, a hard rule under the header, per-tab column
widths, auto-filter, and conditional colours for PR fit, score, and status. The Dashboard
uses the same palette. Re-running a sync restyles the tab.


**Writes are manual only.** There is no auto-sync: nothing reaches the sheet on load, after
a draft, or after a status change. Pitches/Listicles/Coverage go out from a Sync button in
Outreach or Settings. Contacts are never written (the people layer is gone).

**Clearing** is per tab: Settings → Google Sheet sync → pick a tab → Clear. The Apps Script
must be the version that understands `{action:"clear"}` (it deletes data rows in that tab,
keeps the header row and formatting). An older deployment answers `No rows.`, which the
app reports as "does not support clearing yet" — update the script and deploy a new version.

## 8. Behaviour rules now enforced

- **Links**: only public `https` hosts; no `javascript:`, `user@host`, raw IPs,
  localhost, punycode. Unsafe URLs are returned blank and the UI shows "Link withheld".
- **Emails**: must parse, else "Not publicly found".
- **Budget**: validated before spending; rejected requests cost nothing. Every limit is
  checked before any counter is charged, so a refused request cannot burn another one.
- **Budget reporting**: `remaining` = what the next click can use (the smallest of the
  10-minute window, per-browser day, per-IP day, instance day). `today` = the daily
  ceilings only. The sidebar shows `today`; the 10-minute window appears only when it is
  running low. Do not label the window "today" again.
- **One paid attempt per click**: the browser retries only a lost session (401/403), never
  a 5xx, and the API does not re-run a paid action. Both are deliberate: a retry of a
  failed research call spends another call.
- **Time budget**: one action must finish within 240s (`AGENT_TOTAL_BUDGET_SECONDS`,
  incl. the one schema repair), inside the 300s function limit. OpenAI timeout 90s, SDK
  retries 1. A timeout returns 504 with a plain message instead of hanging.

- **Blog only**: research lists blog/editorial URLs; product/pricing/docs pages dropped.
- **One prospect per site** for PR opportunities (strongest kept); listicles not deduped.
- **Reject site**: permanent per-browser domain block, managed in Settings.
- **Used marks**: URL-normalised, survive reloads, exported/imported.
- **Pitches**: 70–150 words, 2–3 paragraphs, one greeting, one ask, fixed sign-off,
  subject ≤60 chars, no AEO, no banned buzzwords — enforced by `enforce_email_rules()`.
  Addressed to the editorial team ("Hi there,"); no recipient name or email is researched
  or invented.
- **Regenerate** produces a deliberately different draft (revision + previous text).

## 9. Known landmines (read before changing anything)

1. **Bulk actions cost real money.** One call per site; always respect the confirm
   dialog. Bulk writers ≈ 4 calls, all pitches ≈ 5–10.
2. **Rate limits are per-instance memory unless a store is configured.** With
   `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` set, the daily and window counters
   live in one Redis (`api/_store.py`): a cold start cannot reset them and every instance
   shares them. Without those vars the caps are a per-instance brake. If the store is
   configured but unreachable, the guard fails closed (503) rather than running uncapped;
   `/api/analyze` reports `budgetStore: shared | memory | degraded` so the UI can say which
   mode is active. The absolute ceiling on the bill is the OpenAI project spend limit — set
   that in the OpenAI dashboard, because no app counter can bound a leaked key.
3. **State is browser-local** (campaigns, library, used, rejected, outcomes). Settings →
   Backup this browser → Export/Import JSON is the only safety net. The app remembers the
   last export and shows a sidebar warning after 14 days without one.
4. **Deploy lag**: after a push, builds take ~60–120s. Verify with a fresh chunk name
   before claiming a fix is live.
5. **Minification** renames functions; verify fixes by user-visible strings, not
   internal names.
6. **`api/analyze.py` runs as a Vercel Python function**; imports must stay inside
   `vercel-app/` (`agent.py`, `_security.py`, `dr.py`).
7. **Middleware matcher** is limited to `/` and `/api/token`; the Python guard
   re-checks the cookie itself.
8. **Local Streamlit app** (`app.py`, `database.py`) is separate; it has the same
   research logic in the root `agent.py` and is not audited to the same level.
9. **The site is behind Cloudflare**, and the API keys rate limits off `x-real-ip`. With
   one user that is harmless, but any second user could share the same counters. Check
   what Vercel sees before adding people.
10. **A leaked password is an OpenAI bill.** One shared password, a one-year HMAC cookie,
    and soft counters. Rotating `SITE_PASSWORD` revokes everyone (and needs a redeploy).


## 10. Open / next

- Freeze features; run three real campaigns and fix only what breaks.
- Listicle policy caching for multi-item runs (contacts already cached).
- Mobile layout check (desktop-first today).
- Decide whether to add the shared budget store (Upstash/Vercel KV, 2 env vars). The code
  path is built and tested; without the vars the app says "no shared counter configured".
  This is the only way to make the daily caps hard.
- Set the OpenAI project spend limit. It is the real ceiling behind everything else.
- Per-user login and retiring the public demo are **closed**: one user, shared gate.


## 11. Quick verification commands

```powershell
# health + remaining budget (no spend)
curl -s https://pr.prachiadmane.com/api/analyze

# gate still on
curl -s -o NUL -w "%{http_code}" https://pr.prachiadmane.com/

# sheet wiring
curl -s https://pr.prachiadmane.com/api/sheet

# latest production build
vercel ls --scope prachi-8a13
```
