# Digital PR Agent

A local Streamlit research assistant for **Digital PR** and **listicle prospecting**.
It turns published articles into PR angles and editorial opportunities, finds
listicle / roundup / alternatives / directory pages where a brand may fit,
researches publisher contacts and publisher inclusion policies, and stores
everything in a local SQLite database for human review.

**The app never emails publishers, submits forms, or sends outreach.** Every
outreach step requires a human to act on the research manually.

The target brand is configurable: set `BRAND_NAME` and `PRODUCT_DESCRIPTION`
(see "Brand configuration" below). The defaults are neutral so the project can
be shared or reused for any product.

## What it does

- Analyse a published article into PR angles and statistics.
- Research digital PR opportunities (journalists, publications, pitch angles).
- Find listicle prospects (roundups, alternatives, directories, comparisons).
- Research publisher contacts and publisher inclusion policies.
- Track review decisions, contact findings, policy findings, and placement status.
- Export prospects and decisions to CSV.
- Create verified database backups.

## Local data stays local

Research data (contacts, policy findings, decisions) lives in a local SQLite
database under `data/` and is **not** committed to this repository. Backups
live under `backups/`. The application creates these folders at runtime.

## Requirements

- Windows (the one-click launchers are `.vbs` / `.bat`)
- Python 3.11+ (tested on 3.14.7)
- An OpenAI API key with access to a nano model

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Set your OpenAI API key in the Windows environment:

```powershell
setx OPENAI_API_KEY "sk-..."
```

Then restart the app or terminal.

## Brand configuration (optional)

To research a specific brand instead of the neutral default, set:

```powershell
setx BRAND_NAME "Your Brand"
setx PRODUCT_DESCRIPTION "a social media management platform"
setx BRAND_DOMAIN "example.com"   # optional, for URL hints only
```

Legacy `VISTA_*` variable names are still accepted as fallbacks.

## Run

One-click (recommended):

- Double-click `launch_pr_agent_hidden.vbs` to start.
- Open `http://localhost:8501`.
- Double-click `stop_pr_agent.bat` to stop.

From a shell:

```powershell
streamlit run app.py
```

## Health check (one click)

Double-click `run_storage_check.vbs`. It runs the full storage test against a
temporary database, saves a prospect at every stage, restarts the session,
exports data, creates a backup, and verifies the backup. It never touches the
real research database and does not call the OpenAI API. Full details are
written to `backups\latest_storage_check.txt`.

## Model and cost

The default model is **`gpt-5.4-nano`** (a low-cost nano model). Override it
with an environment variable before launching:

```powershell
setx OPENAI_MODEL "gpt-5-nano"        # lowest per-token price
setx OPENAI_MODEL "gpt-4.1-nano"
```

(Legacy name `VISTA_OPENAI_MODEL` is also accepted.)

Web-search context size (affects search token cost) can also be tuned:

```powershell
setx SEARCH_CONTEXT_SIZE "medium"          # low | medium | high (default: high)
```

The active model is shown in the app sidebar.

## Deploy to Render (recommended for full app)

The repo includes a `render.yaml` blueprint for one-click deploy on Render with a
persistent disk (so your research database and backups survive restarts).

1. Push this repo to GitHub (already done).
2. Go to https://render.com → "New" → "Blueprint" → connect your repo.
3. Render reads `render.yaml` and creates the web service + disk.
4. In the service's "Environment" tab, set `OPENAI_API_KEY` (and optionally
   `BRAND_NAME`, `PRODUCT_DESCRIPTION`).
5. Deploy. Your app will be live at `https://<name>.onrender.com`.

The disk is mounted at the project's `data/` folder, so the SQLite database and
backups persist across deploys and restarts.

For Railway instead, use the included `Procfile` and add a persistent volume
mounted at the project root.

- `.gitignore` excludes `.venv/`, `data/`, `backups/`, logs, and local code
  snapshots. Research data never leaves this machine through git.
- Publisher research is informational and must be checked by a human.
- Policy findings are recommendations, not permission or a placement guarantee.
- The app does not contact publishers or send outreach.

## Project structure

- `app.py` - Streamlit UI.
- `agent.py` - OpenAI Agents SDK research agents and prompts.
- `database.py` - SQLite storage, backups, exports, migrations.
- `storage_self_check.py` - end-to-end storage test (43 checks).
- `run_storage_check.vbs` - one-click health check.
- `install_persistent_storage_update.vbs` - update installer with rollback.
- `README.txt` - local user guide.

## Updating

Use `install_persistent_storage_update.vbs` only when you have a full update
package containing `agent.py`, `app.py`, and `database.py`. It stops the app,
backs up your current code and database, installs the files, checks Python
syntax and required functions, and rolls back on failure. Older single-feature
installers live in `backups\legacy-installers` and should not be used.
