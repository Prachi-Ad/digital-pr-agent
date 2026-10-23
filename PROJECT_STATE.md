# Digital PR Agent - Project State

Last updated: Fri Oct 23 2026

## Objective

A local Streamlit research assistant for Digital PR and listicle prospecting.
It turns published articles into PR angles, finds editorial and listicle
opportunities, researches publisher contacts and policies, prepares outreach
drafts for human review, and stores everything locally. From the local app, it
can send explicitly approved drafts through the configured Gmail account
(currently the personal Gmail app-password connection) in a confirmed batch with
a delay, a daily cap, a do-not-send list, and an audit log. It never submits
publisher forms.

## Current UI

Three pages only:

1. **Workspace** - one guided workflow with two paths:
   - Digital PR: Article -> PR angles -> Opportunities -> Journalists -> Outreach.
   - Listicles: Search -> Prospects (contacts/policy) -> Outreach.
2. **Research Library** - listicles, PR opportunities, journalists, outreach
   drafts, email send history, CSV exports, backups.
3. **Settings** - brand, sender details, email sending (OAuth, app password, or
   custom SMTP), do-not-send list, model/cost, storage, safety.

The old separate pages (Dashboard, PR Home, Asset Analysis, PR Action Plans,
Outreach, etc.) were merged into the guided Workspace. Saved work is restored
after a restart, and the start screen offers both "Continue saved..." and
"Start new..." buttons for each workflow.

### Vercel demo UI
The Vercel deployment is a Next.js visual port of the same interface: fixed
left sidebar, "Working for Vista Social" chip, Workspace / Research Library /
Settings navigation, WORKSPACE eyebrow, workflow stepper, indigo palette, and
compact research cards. The old dashboard/tab layout is gone. Settings shows
the fixed sender identity, Prachi, SEO Specialist, and a read-only preview of
the local email-sending setup: the three sending methods, the active
personal-Gmail app-password method, batch safeguards, and the do-not-send list.
The preview collects no credentials and cannot send. The local Streamlit app
remains the full tool. The Vercel Article step also accepts up to five URLs, but
keeps results in memory only; the port does not add saved libraries, draft
generation, accounts, quotas, billing, or email sending. Every generated
result exposes a Generate again or Refresh control that re-runs the same
research action; these controls do not add persistence or sending. Vercel stays
a non-sending demo.

## Completed work

### Storage (validated)
- Full storage check passes: listicles, contacts, policy, review decisions,
  placement progress, PR opportunities, journalists, co-authors, outreach
  drafts, restart/restore, exports, backups, and edge cases.
- New `outreach_drafts` table with human edits and status tracking, plus
  recipient email, send timestamp, message ID, last send error, and attempt count.
- `email_sends` audit table stores every send attempt (sent or failed) with the
  recipient, subject, body hash, message ID, and error. CSV export is available.
- `email_suppressions` table stores the local do-not-send / opt-out list.
- `storage_self_check.py` now covers outreach drafts and currently passes all checks.
- Streamlit AppTest smoke run completes with no exceptions on Workspace, Settings,
  and Research Library.
- Backup integrity verification and CSV formula-injection protection remain.
- Older saved payloads missing newly added fields are accepted with safe defaults.

### Outreach preparation
- New `OutreachDraft` structured model and draft agent (no web search).
- Digital PR pitch and listicle inclusion request generation.
- Human-editable subject/body, recipient email, status, verification checklist,
  and text download.
- Draft status: Draft, Approved for automated send, Approved for manual send,
  Sent, Send failed, Sent manually, Replied, Placement confirmed, Declined,
  Do not send.
- Fixed sender identity in every draft: Prachi, SEO Specialist.
- Batch sending is opt-in only: a draft must be marked "Approved for automated
  send", then a separate batch confirmation is required.
- No form submission, ever.

### Local email batch sending
- Gmail / Google Workspace SMTP through `smtp.gmail.com` on port 587 with
  STARTTLS. Three authentication methods are supported:
  - **Google app password** (requires 2-Step Verification and an admin who
    allows app passwords).
  - **Google Workspace sign-in (OAuth 2.0)** with SMTP XOAUTH2 for work/school
    accounts where app passwords are blocked.
  - **Custom SMTP / designated email** for any provider that supplies a
    designated From address plus SMTP host, port, username, and password/API
    key. Supports STARTTLS (usually 587) and SSL/TLS (usually 465).
- Settings stores the Gmail address, app password, OAuth client ID/secret,
  refresh token, custom SMTP host/port/username/password/security, delay, daily
  cap, and optional mailing address in `data/email_config.json`, which is
  gitignored. The From name stays fixed as Prachi, SEO Specialist.
- Default delay is 30 seconds between sends (configurable 5-300). Default daily
  cap is 20 successful sends per local day (configurable 1-200).
- The batch panel is on both Outreach pages. It lists only approved drafts, shows
  the exact messages, and requires a confirmation checkbox before sending.
- Sending is sequential. The UI shows progress and a delay countdown.
- Every email gets an automatic opt-out line and `List-Unsubscribe` header; the
  optional mailing address is appended when configured.
- Missing/invalid recipient email, missing subject/body, an existing sent record,
  an opt-out match, or daily-cap overflow blocks the batch.
- Fatal SMTP authentication/connection errors stop the batch. Delivery-uncertain
  errors are called out so the recipient can be checked before retrying.
- Every attempt is recorded in `email_sends` and shown in the Research Library
  "Email send log" tab with CSV export.
- The do-not-send list in Settings blocks matching addresses from every future
  batch. Add opted-out recipients there as soon as they ask.
- Sending is available only from the local Streamlit app. There is no scheduler,
  background worker, or unattended sending.
- The local launchers bind Streamlit to `127.0.0.1` so the unauthenticated
  sending UI is not exposed to other devices on the network.
- Vercel remains a non-sending demo.

### Active local sender
- Active method: **Google app password**.
- Active account: **personal Gmail** (configured only in the local, gitignored
  `data/email_config.json`).
- SMTP login test: **passed**; no email was sent.
- No work Google account, Google OAuth client, refresh token, or custom SMTP
  mailbox is connected.
- The OAuth and Custom SMTP options remain available in Settings for optional
  future use, but they are unconfigured. The app is not using a work account.

### Optional Google Workspace OAuth connection
- **Not configured in the current personal-Gmail setup.** This exists for a
  future, explicitly approved Workspace connection.
- Settings has a **Sending method** choice: **Google app password**, **Google
  Workspace sign-in (OAuth)**, or **Custom SMTP / designated email**. Changing
  the radio saves `auth_method` immediately.
- The OAuth flow is a local Web application flow:
  - Google Cloud OAuth client type: **Web application**.
  - Authorized redirect URI: `http://localhost:8501/`.
  - Scopes: `openid`, `email`, `https://mail.google.com/`.
  - `access_type=offline` and `prompt=consent select_account` so Google returns
    a refresh token and lets the user choose the Google account.
- OAuth state is a random token stored briefly in
  `data/oauth_state.json`, validated once, and deleted. The callback is handled
  at the top of `app.py` before normal navigation and routes back to Settings.
- Token exchange, userinfo verification, token refresh/cache, config
  persistence, and SMTP XOAUTH2 login are implemented in `email_sender.py` using
  the standard library (`urllib`, `smtplib`); no new Python dependency was
  added.
- Settings shows the exact redirect URI, a **Connect/Reconnect Google Workspace
  account** link, connection status, **Test Google sign-in**, and **Disconnect
  Google account**. The app password form remains available as a fallback.
- **Internal** OAuth consent screen is recommended for a Workspace org. External
  testing works but Google expires refresh tokens after 7 days and an unverified
  app warning appears.
- A custom local app must use its own Google Cloud OAuth client; it cannot reuse
  Instantly's or ContactOut's client. A Workspace admin may need to allow the
  OAuth app/client ID and the Gmail scope. This is not a bypass of admin policy.
- Gmail SMTP over OAuth requires the broad `https://mail.google.com/` scope. The
  app only logs in and sends; it does not read mail.
- Mocked tests cover URL construction, state validation/expiry, token exchange,
  userinfo, refresh/cache, XOAUTH2 auth string, fake SMTP send/test, disconnect,
  config persistence, all three Settings modes, and the callback
  routing/notice. Real Google OAuth has not been exercised because no client
  ID/secret or Google account has been connected.

### Optional Custom SMTP / designated sender
- **Not configured in the current personal-Gmail setup.** This exists for a
  future mailbox that supplies its own SMTP credentials.
- The third Settings mode lets the user enter any designated From address and
  the provider's SMTP host, port, username, password/API key, and connection
  security (STARTTLS or SSL/TLS).
- Custom SMTP credentials are stored separately from the Google app password, so
  switching modes does not overwrite the other provider's secret. OAuth client
  details and refresh tokens are also preserved.
- Gmail/Workspace modes force `smtp.gmail.com:587` STARTTLS internally, so a
  saved custom host cannot accidentally change Google sending. Custom SMTP uses
  its own host/port/security.
- Custom SMTP requires a valid From address, host, username, and password in the
  local config. The provider must permit the From address/domain.
- Google Workspace still normally requires OAuth, an admin-enabled app password,
  or an admin-approved SMTP relay. A normal Google password is not accepted.
- No new Python dependency; custom SMTP uses `smtplib` and the existing send
  pipeline. Mocked tests cover config persistence, missing-field checks, login
  arguments, STARTTLS/SSL, send, test, and the Settings UI.

### Batch article analysis
- The Article step starts with one URL field. "+ Add URL" adds up to five
  separate HTTPS fields; "− Remove last" removes the most recent field.
- Empty fields are ignored, and duplicate URLs are deduplicated before analysis.
  Invalid URLs are rejected with a clear message.
- Each URL gets its own asset analysis. Partial failures are reported per URL,
  and successful analyses are kept.
- Analyses are stored in `asset_analyses`, keyed by the input URL, and persisted
  in the workspace snapshot.
- Saved analyses are reused by default to avoid repeat API spend. The optional
  "Re-analyze URLs already saved" checkbox forces fresh calls.
- "Use this article" switches the active asset. Switching articles clears stale
  PR angles, opportunities, reviews, and journalist results before the next step.
- The active asset still drives the existing PR angles -> Opportunities ->
  Journalists -> Outreach flow.
- The Vercel demo mirrors the same add/remove URL fields, sequential analysis,
  active article selection, and downstream reset, but keeps results in browser
  memory only.

### Cost
- Default model changed to `gpt-5-nano` (cheapest standard nano).
- Search context defaults to `low`; max turns 3.
- Listicle searches can be limited to 5, 10, 15, or 20 candidate pages per run.
- Article analysis runs once per new URL, up to five per batch. Saved analyses
  are reused unless "Re-analyze URLs already saved" is checked.
- On-demand contact/policy/journalist research only.
- Draft generation uses no web search and one short model call.
- Optional `gpt-5-nano-flex` for lower per-token cost.

### UX / decluttering
- One Workspace with a short stepper instead of nine separate pages.
- "Switch workflow" reliably returns to the mode chooser; workflow inference
  runs only on first load, so it no longer undoes a manual switch.
- Active workflow pages use one compact header. The workflow name replaces the
  generic page title, and large step headings were folded into short captions.
- Global library totals appear on the mode chooser and Research Library only.
  Active review pages use a compact four-number queue strip; filter labels stay
  short (Needs review / Approved / All).
- Auto-save review selects; removed repetitive Save buttons.
- Needs review / Approved / All filters on the prospect and PR opportunity lists.
- Review cards keep title, metadata, and the open-page action in one header.
  Full details, evidence, and optional contact/policy research sit behind one
  expander, so the list stays scannable.
- Streamlit theme primary is indigo `#5b5bd6`; the old red theme is gone, and
  primary buttons use the indigo gradient.
- Brand config in `data/brand_config.json`, editable in Settings, including an
  optional website / `BRAND_DOMAIN`.
- Sender identity is hardcoded to Prachi / SEO Specialist and used in every
  outreach draft. The editable sender fields are now read-only. Existing drafts
  with [Your name] / [Your role] placeholders were migrated to the fixed identity.
- Sidebar uses three small monochrome CSS-mask icons; no emoji or icon-heavy rows.
- Tighter 12px vertical rhythm and compact metric tiles.
- Vercel demo rebuilt to mirror the local workspace: left sidebar, workspace
  badge, stepper, indigo cards, expandable action plans, and inline
  contact/policy results. Red error styling was removed.
- CORS configuration corrected for local Streamlit.

### Reliability
- Journalist research could fail on a later run with
  `RuntimeError: Event loop is closed`. Each call created a fresh thread and
  `asyncio.run` loop, then closed it while the shared `AsyncOpenAI` client still
  referenced it.
- `agent.py` and `vercel-app/agent.py` now keep one event loop alive per process
  and create the shared OpenAI client lazily on that loop. Sequential and
  concurrent agent calls reuse the same open loop.
- Verified with a fake `Runner.run` across repeated and concurrent calls, a
  Streamlit UI smoke test, and the full local storage check.
- Fix commit: `acd5c9d`; the Vercel production deployment uses the same code.
- The real workspace snapshot was restored from
  `backups/pr_agent_before_sender_hardcode_20261022-174929.sqlite3` after a test
  AppTest run saved fake batch analyses into the live database. Future AppTest
  runs should set `PR_AGENT_DATA_DIR` to a temporary directory so they cannot
  overwrite the live workspace.

### Hosting and repo
- GitHub repository: `https://github.com/Prachi-Ad/digital-pr-agent` (private).
  Branch `main`; old versions remain recoverable in history.
- Render blueprint and Railway Procfile remain optional.
- Vercel demo is deployed (see Deployment below).
- `.gitignore` excludes `.venv/`, `data/`, `backups/`, and secrets.
- Local brand file, email credentials, and database stay out of git.
- `install_persistent_storage_update.vbs` now installs, backs up, and rolls back
  `email_sender.py`, and its smoke check covers the email-sending functions.

### Deployment (live)
- Vercel project: `vercel-app` under team `prachi-8a13`.
- Production URL: `https://vercel-app-gules-three.vercel.app`
- Git integration root directory: `vercel-app`. Vercel must build the Next.js
  demo from this subfolder, not the Streamlit repository root.
- Deployment: Vercel Git integration builds the `vercel-app` subfolder on each
  push to `main`; the production alias is verified healthy.
- Code deployed: `5b3096a` (Generate again and Refresh controls for article
  analysis, PR angles, opportunities, journalists, listicles, contact research,
  and publisher policy), building on the read-only email Settings preview in
  `4574646` and earlier Vercel UI parity work.
- Status: READY; production alias live as of 2026-10-23. Latest UI deployment:
  `https://vercel-kc0pkjkzt-prachi-8a13.vercel.app`. Public alias:
  `https://vercel-app-gules-three.vercel.app`.
- Batch article analysis was verified on the public alias: "+ Add URL" creates
  up to five separate fields, a sixth field is prevented, and non-HTTPS URLs
  show the validation message.
- Vercel environment: `OPENAI_API_KEY` is configured for Production,
  Preview, and Development (value not stored in the repo).
- Build verified: Git-triggered Next.js 14.2.15 production build succeeds;
  the public alias root and `/api/analyze` both return 200. The Settings preview
  was verified locally and on the public alias: all three methods render, the
  app-password preview is active, and the page clearly states that this demo
  collects no credentials and cannot send email.
- Generate again and Refresh controls were verified locally and on the public
  alias with stubbed research responses, so no live research calls were
  consumed. They re-run the existing analysis, opportunities, journalists,
  listicles, contact, and policy actions without adding persistence or sending.
- Demo scope: the Vercel app can call analyze, PR opportunities, journalists,
  listicles, contact, and policy research actions. Its UI now mirrors the local
  workspace, but it does not have persistence, accounts, review-library storage,
  draft generation, usage quotas, billing, or email sending.
- The email batch sender is local-only and intentionally not part of the
  Vercel build. Pushes that only change local sending code should use
  `[skip vercel]` so the non-sending demo is not redeployed needlessly.
- The full tool remains the local Streamlit app. No custom domain is connected
  to Vercel yet.

## Known caveats

- Web search dominates cost (~$10 per 1,000 calls). Research runs only on click.
- The Vercel demo is a Next.js visual port, not the Streamlit runtime. It covers
  the research actions but has no persistence, accounts, quotas, review library,
  or draft generation. The local Streamlit app is the full tool.
- The Vercel demo accepts up to five article URLs per batch, but analyses are
  kept only in browser memory and are lost on reload.
- A saved PR opportunity queue can be reviewed after a restart without the
  original full asset analysis. Re-analyzing the article restores journalist
  research for new candidates.
- Sending is currently configured with the **personal Gmail app password**; the
  SMTP login test passed. No work Google account, OAuth client, refresh token, or
  custom SMTP mailbox is connected. No real email has been sent.
- `data/email_config.json` (gitignored) may contain an app password, custom SMTP
  password, OAuth client secret, and refresh token in plaintext. Protect the
  machine and revoke/rotate credentials if the file is exposed.
- The optional Gmail SMTP OAuth path uses the broad `https://mail.google.com/`
  scope. A Workspace admin may block the custom OAuth client or this scope. The
  app surfaces the failure; it does not bypass admin policy.
- Optional External OAuth testing clients get 7-day refresh tokens. Use an
  Internal client for a durable Workspace connection.
- The app does not read replies. If someone opts out, add their address to the
  do-not-send list manually.
- The daily cap counts successful sends. A dropped connection can be ambiguous;
  the UI warns before a retry.
- Vercel cannot send email and remains a visual demo.

## Recommended next steps

1. Add a physical mailing address in Settings if not already set; it is appended
   to every outgoing email.
2. Add a verified recipient email to one draft, mark it "Approved for automated
   send", and run a one-recipient batch as a live test. Review the send log.
3. Run one real Digital PR workflow end-to-end with the nano model and review output quality.
4. Run one real listicle workflow end-to-end, including contact and policy research.
5. Test one generated pitch and one inclusion request, then edit and track status.
6. Decide whether to keep the Vercel demo public, put it behind login, or retire
   it. Before a public launch, add accounts, per-user data isolation, spend
   caps, and a custom domain.

The OAuth and Custom SMTP modes remain available but unconfigured. The active
sender is the personal Gmail app password. Connect a work or custom mailbox only
if you intend to use it and have the required approval.
