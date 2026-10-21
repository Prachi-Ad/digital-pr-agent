# Vista Social PR Agent - Project State

Last updated: Wed Oct 21 2026

## Objective

A local Streamlit research assistant for Digital PR and listicle prospecting at
Vista Social. The app turns published Vista Social articles into PR angles and
editorial opportunities, finds listicle / roundup / alternatives / directory
pages, researches publisher contacts and inclusion policies, and stores
everything in a local SQLite database. It never emails publishers, submits
forms, or sends outreach automatically.

## Completed work

### Storage hardening (validated)
- Full storage validation passed with a temporary DB and a copy of the real DB.
- Fixed `updated_at` churn: page views now only refresh `last_seen`.
- Contact, policy, and journalist research now save immediately.
- Fixed critical journalist co-author collision: person-specific keys plus
  automatic legacy migration.
- Recovered journalist Catherine Wolf; real DB now has 18 listicles, 9 PR
  opportunities, 3 journalists.
- Repaired `install_persistent_storage_update.vbs` (`smokePath` declaration,
  same-folder self-copy guard); tested both branches.
- Added backup integrity verification and CSV formula-injection protection.
- Added `storage_self_check.py` and `run_storage_check.vbs`; all 43 checks pass.
- Moved stale `install_publisher_policy_update.vbs` to
  `backups\legacy-installers\`.
- Added `.gitignore`, `.gitattributes`, `requirements.txt`, `README.md`,
  `README.txt`, `PROJECT_STATE.md`.

### Model / cost
- Switched all six agents to `model=MODEL` with default `gpt-5.4-nano`.
- Added `VISTA_OPENAI_MODEL` and `VISTA_SEARCH_CONTEXT` overrides.
- Live-tested `analyze_article` with `gpt-5.4-nano`: succeeded in ~30s, 5
  angles, 20 statistics.
- Added model caption to app sidebar.
- Verified `gpt-5.4-nano` and `gpt-5-nano` both support the web-search tool
  and structured output.

### GitHub preparation
- `.gitignore` excludes `.venv/`, `data/`, `backups/`, logs, secrets, and
  local code snapshots.
- `requirements.txt` pins the tested dependency versions.
- `README.md` documents setup, model config, privacy, and health checks.
- GitHub CLI is authenticated as `Prachi-Ad` with `repo` scope.
- Repo `Prachi-Ad/vista-pr-agent` does not exist yet.

## Remaining work

1. Initialize git in the project folder and make the first commit.
2. Create the private GitHub repo `Prachi-Ad/vista-pr-agent` and push.
3. Verify the remote contains only code/docs (no DB, backups, venv, secrets).
4. Run `storage_self_check.py` once more after any further code edits.
5. Decide whether to make the repo public later (currently private by design).

## Known bugs / caveats

- None blocking. All 43 storage checks pass.
- `gpt-5-nano` is cheaper per token but used ~2,800 reasoning tokens on a
  trivial task in testing; `gpt-5.4-nano` is the default for reliability.
- Web search calls dominate cost (~$10 per 1,000 calls); model choice alone
  cannot remove that.
- Git and GitHub CLI are not on PATH on this machine; use full paths
  (`C:\Program Files\Git\cmd\git.exe`, `C:\Program Files\GitHub CLI\gh.exe`).

## Important decisions

- Validation scope: "Validate + harden storage".
- Default model: `gpt-5.4-nano` (newest nano, far fewer output tokens in
  testing than `gpt-5-nano`).
- GitHub repo will be private by default (proprietary PR logic); local DB and
  backups excluded.
- Existing research data stays local; GitHub gets code/docs only.
- No automatic outreach, ever.

## Recommended next steps

1. Run `git init`, stage, commit with full paths to git.
2. Create and push the private repo with `gh`.
3. Verify remote file list excludes `.venv/`, `data/`, `backups/`.
4. Run `storage_self_check.py` again and report results.
5. Optionally test `research_listicles` end-to-end with the nano model.
