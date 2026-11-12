# Handoff — Digital PR Research Agent

Last updated: 2026-11-12
Live: https://pr.prachiadmane.com (Vercel, Next.js 14.2.35 + Python API)
Repo: https://github.com/Prachi-Ad/digital-pr-agent (branch `main`)
Local path: `C:\Users\Prachi\vista-pr-agent`

---

## 1. What this is

A research-only Digital PR tool for Vista Social. It turns a published article (yours
or a publisher's) into pitch angles, finds publisher articles worth pitching, finds the
writer or content/SEO contact, writes a pitch, and logs everything to Google Sheets.
**It never sends email and never submits forms.** The local Streamlit app is the legacy
full tool; the Vercel app is the primary one.

## 2. Live surface

| Area | Path | Notes |
| --- | --- | --- |
| Sign-in | `/login` | Shared password gate, signed `pr_auth` cookie |
| App | `/` | Workspace → Research Library → Settings |
| Sheet sync | `/api/sheet` | Apps Script webhook; upsert by key |
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

Python API actions: `analyze`, `own-pages`, `domain-scan`, `opportunities`,
`journalists`, `person-contact`, `draft`, `listicles`, `listicle-contact`,
`listicle-draft`, `publisher-policy`, `collect-writers`, `site-metrics`.

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
25 tests: URL/email sanitizing, blog-only filter, email rules enforcement, precheck
(no budget spent on invalid requests), dedupe.

## 7. Google Sheet

Tabs: **Dashboard**, **Pitches**, **Listicles**, **Contacts**, **Coverage**.
Script source lives at `vercel-app/apps-script/pitch-sheet.gs` (token redacted) and is
served at `/apps-script/pitch-sheet.js` for the "Copy setup script" button.
Rule: every Apps Script change needs **Deploy → Manage deployments → New version**, and
a *new deployment* yields a **new `/exec` URL** that must be re-entered in Vercel.

## 8. Behaviour rules now enforced

- **Links**: only public `https` hosts; no `javascript:`, `user@host`, raw IPs,
  localhost, punycode. Unsafe URLs are returned blank and the UI shows "Link withheld".
- **Emails**: must parse, else "Not publicly found".
- **Budget**: validated before spending; rejected requests cost nothing.
- **Blog only**: research lists blog/editorial URLs; product/pricing/docs pages dropped.
- **One prospect per site** for PR opportunities (strongest kept); listicles not deduped.
- **Reject site**: permanent per-browser domain block, managed in Settings.
- **Used marks**: URL-normalised, survive reloads, exported/imported.
- **Pitches**: 70–150 words, 2–3 paragraphs, one greeting, one ask, fixed sign-off,
  subject ≤60 chars, no AEO, no banned buzzwords — enforced by `enforce_email_rules()`.
- **Regenerate** produces a deliberately different draft (revision + previous text).

## 9. Known landmines (read before changing anything)

1. **Bulk actions cost real money.** One call per site; always respect the confirm
   dialog. Bulk writers ≈ 4 calls, all pitches ≈ 5–10.
2. **Rate limits are per-instance memory.** Multiple Vercel instances each keep their
   own counters, so the daily cap is best-effort. A shared Redis counter would fix it.
3. **State is browser-local** (campaigns, library, used, rejected, outcomes). Settings →
   Backup this browser → Export/Import JSON is the only safety net.
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

## 10. Open / next

- Move rate limits to a shared store for a hard global spend cap.
- Freeze features; run three real campaigns and fix only what breaks.
- Listicle policy caching for multi-item runs (contacts already cached).
- Mobile layout check (desktop-first today).
- Decide whether to keep the public demo, put it behind per-user login, or retire it.

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
