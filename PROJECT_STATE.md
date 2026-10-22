# Digital PR Agent - Project State

Last updated: Thu Oct 22 2026

## Objective

A local Streamlit research assistant for Digital PR and listicle prospecting.
It turns published articles into PR angles, finds editorial and listicle
opportunities, researches publisher contacts and policies, prepares outreach
drafts for human review, and stores everything locally. It never sends email,
submits forms, or contacts publishers.

## Current UI

Three pages only:

1. **Workspace** - one guided workflow with two paths:
   - Digital PR: Article -> PR angles -> Opportunities -> Journalists -> Outreach.
   - Listicles: Search -> Prospects (contacts/policy) -> Outreach.
2. **Research Library** - listicles, PR opportunities, journalists, outreach
   drafts, CSV exports, backups.
3. **Settings** - brand, sender details, model/cost, storage, safety.

The old separate pages (Dashboard, PR Home, Asset Analysis, PR Action Plans,
Outreach, etc.) were merged into the guided Workspace. Saved work is restored
after a restart, and the start screen offers both "Continue saved..." and
"Start new..." buttons for each workflow.

## Completed work

### Storage (validated)
- Full storage check passes: listicles, contacts, policy, review decisions,
  placement progress, PR opportunities, journalists, co-authors, outreach
  drafts, restart/restore, exports, backups, and edge cases.
- New `outreach_drafts` table with human edits and status tracking.
- `storage_self_check.py` now covers outreach drafts and currently passes all checks.
- Streamlit AppTest smoke run completes with no exceptions on Workspace, Settings,
  and Research Library.
- Backup integrity verification and CSV formula-injection protection remain.
- Older saved payloads missing newly added fields are accepted with safe defaults.

### Outreach preparation
- New `OutreachDraft` structured model and draft agent (no web search).
- Digital PR pitch and listicle inclusion request generation.
- Human-editable subject/body, status, verification checklist, and text download.
- Draft status: Draft, Approved for manual send, Sent manually, Replied,
  Placement confirmed, Declined, Do not send.
- No sending or form submission, ever.

### Cost
- Default model changed to `gpt-5-nano` (cheapest standard nano).
- Search context defaults to `low`; max turns 3.
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
- Sender name/role stored in the workspace and used in drafts.
- Sidebar uses three small monochrome CSS-mask icons; no emoji or icon-heavy rows.
- Tighter 12px vertical rhythm and compact metric tiles.
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

### Hosting and repo
- GitHub repository: `https://github.com/Prachi-Ad/digital-pr-agent` (private).
  Branch `main`; old versions remain recoverable in history.
- Render blueprint and Railway Procfile remain optional.
- Vercel demo is deployed (see Deployment below).
- `.gitignore` excludes `.venv/`, `data/`, `backups/`, and secrets.
- Local brand file and database stay out of git.

### Deployment (live)
- Vercel project: `vercel-app` under team `prachi-8a13`.
- Production URL: `https://vercel-app-gules-three.vercel.app`
- Git integration root directory: `vercel-app`. Vercel must build the Next.js
  demo from this subfolder, not the Streamlit repository root.
- Deployment ID: `dpl_ESYwz7rCLC6YNi7Xd9e15EbtRgdT`
- Code deployed: commit `acd5c9d` (persistent event-loop fix); Git-triggered
  build from commit `429c40d`.
- Status: READY; production alias live as of 2026-10-22. The Git-triggered
  deployment builds the `vercel-app` subfolder and serves the demo correctly.
- Vercel environment: `OPENAI_API_KEY` is configured for Production,
  Preview, and Development (value not stored in the repo).
- Build verified: Git-triggered Next.js 14.2.15 production build and Python
  dependencies complete successfully; root and `/api/analyze` both return 200.
- Demo scope: the Vercel app can call analyze, PR opportunities, journalists,
  listicles, contact, and policy research actions. It does not yet have
  persistence, accounts, review-library storage, usage quotas, or billing.
- The full tool remains the local Streamlit app. No custom domain is connected
  to Vercel yet.

## Known caveats

- Web search dominates cost (~$10 per 1,000 calls). Research runs only on click.
- The Vercel demo covers the research actions but has no persistence, accounts,
  quotas, or review library. The local Streamlit app is the full tool.
- A saved PR opportunity queue can be reviewed after a restart without the
  original full asset analysis. Re-analyzing the article restores journalist
  research for new candidates.
- The app never sends outreach. Every send is manual.

## Recommended next steps

1. Run one real Digital PR workflow end-to-end with the nano model and review output quality.
2. Run one real listicle workflow end-to-end, including contact and policy research.
3. Test one generated pitch and one inclusion request, then edit and track status.
4. Decide whether to keep the Vercel demo public, put it behind login, or retire
   it. Before a public launch, add accounts, per-user data isolation, spend
   caps, and a custom domain.
