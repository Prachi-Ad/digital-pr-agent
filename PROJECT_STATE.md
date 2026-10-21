# Digital PR Agent - Project State

Last updated: Wed Oct 21 2026

## Objective

A local Streamlit research assistant for Digital PR and listicle prospecting.
The app turns published articles into PR angles and editorial opportunities,
finds listicle / roundup / alternatives / directory pages, researches publisher
contacts and inclusion policies, and stores everything in a local SQLite
database. It never emails publishers, submits forms, or sends outreach
automatically. The target brand is configurable via `BRAND_NAME` /
`PRODUCT_DESCRIPTION` (defaults are neutral so the project can be shared).

## Completed work

### Storage hardening (validated)
- Full storage validation passed with a temporary DB and a copy of the real DB.
- Fixed `updated_at` churn; contact/policy/journalist research save immediately.
- Fixed journalist co-author collision with person-specific keys + migration.
- Repaired installer (same-folder self-copy guard); tested both branches.
- Backup integrity verification and CSV formula-injection protection.
- `storage_self_check.py` (43 checks) and `run_storage_check.vbs`; all pass.
- `.gitignore`, `.gitattributes`, `requirements.txt`.

### Model / cost
- All six agents use `model=MODEL`, default `gpt-5.4-nano`.
- `OPENAI_MODEL` / `SEARCH_CONTEXT_SIZE` overrides (legacy `VISTA_*` accepted).
- Live-tested `analyze_article`: ~30s, 5 angles, 20 statistics.

### Vercel deployment (analyze workflow)
- Created `vercel-app/`: Next.js frontend + FastAPI Python serverless function (`api/analyze.py`).
- Deployed to production: https://vercel-app-gules-three.vercel.app
- `/api/analyze` returns structured article analysis (verified end-to-end).
- Env var `OPENAI_API_KEY` set in Vercel (production/preview/development).
- Remaining workflows (PR opportunities, journalists, listicles, storage) not yet ported.
- Brand is configurable via env vars; defaults are neutral.
- DB filename migrated from `vista_pr_agent.sqlite3` to `pr_agent.sqlite3`
  (one-time rename on startup, data preserved).
- Launchers renamed to `launch_pr_agent_hidden.vbs`, `run_pr_agent.bat`,
  `stop_pr_agent.bat`.

### GitHub
- Private repo `Prachi-Ad/digital-pr-agent` (renamed from vista-pr-agent).
- Contains code/docs only; no DB, backups, venv, or secrets.

## Remaining work

1. Verify renamed repo remote contents and URL.
2. Run `storage_self_check.py` once more after edits.
3. Optionally test `research_listicles` end-to-end with the nano model.
4. Optionally rename the local project folder from `vista-pr-agent` to
   `pr-agent` (not required; installer now uses its own folder).

## Known bugs / caveats

- None blocking. All 43 storage checks pass.
- Web search calls dominate cost (~$10 per 1,000 calls).

## Important decisions

- Default model: `gpt-5.4-nano`.
- GitHub repo private by default; local DB/backups excluded.
- No automatic outreach, ever.
- Brand configurable; neutral defaults for shareability.

## Recommended next steps

1. Run `storage_self_check.py` again and report results.
2. Rename GitHub repo to `digital-pr-agent` and update remote.
3. Verify remote file list excludes `.venv/`, `data/`, `backups/`.
