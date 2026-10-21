# Digital PR Agent

A local Streamlit workspace for **Digital PR** and **listicle prospecting**.
It turns published articles into PR angles, finds editorial and listicle
opportunities, researches contacts and publisher policies, prepares outreach
drafts for human review, and stores every record locally.

**The app never sends email, submits a publisher form, or contacts anyone.**
You approve every decision and send every message yourself.

## The simple workflow

The app has three pages:

1. **Workspace** - the daily workflow. Choose one of two paths:
   - **Digital PR:** article → PR angles → opportunities → journalists → outreach draft.
   - **Listicle inclusion:** search → prospects, contacts, and policy → inclusion request.
2. **Research Library** - saved prospects, PR opportunities, journalists, drafts,
   CSV exports, and verified database backups.
3. **Settings** - brand, sender details, model/cost information, storage, safety.

Each path is a short numbered stepper. Saved work is restored when you reopen
the app, and the Workspace shows a "Continue saved..." button on the start screen.
Active workflow pages stay compact: one header, the stepper, a short context
line, a four-number queue strip, and the review list. Cards keep title, key
metadata, and the main action together, with details and optional research
behind one expander. The interface uses an indigo accent and small monochrome
sidebar icons rather than emoji.

## What each step does

- **Asset analysis:** extracts topics, audiences, claims, statistics, and PR angles.
- **PR opportunities:** finds real existing articles that could fit an angle.
- **Journalist research:** verifies writers through their published work.
- **Listicle research:** finds roundups, alternatives, comparisons, and directories.
- **Contact research:** finds authors, editors, and official contact routes.
- **Publisher policy:** checks whether a publisher accepts inclusion requests,
  uses a paid/affiliate/directory route, or should be skipped.
- **Outreach preparation:** writes a personalized draft using only verified
  research. Drafts are editable and tracked as Draft, Approved for manual send,
  Sent manually, Replied, Placement confirmed, Declined, or Do not send.
- **Tracking:** review decisions and placement progress are saved immediately
  in a local SQLite database.

## Cost controls

The default model is **`gpt-5-nano`**, the cheapest standard nano option. To go
lower, set `OPENAI_MODEL` to `gpt-5-nano-flex` before launching.

- Web search context defaults to **low** (`SEARCH_CONTEXT_SIZE=low`).
- Agent turns are limited to 3 by default (`MAX_TURNS=3`).
- Contact, policy, and journalist research run only when you click their buttons.
- Outreach drafts use **no web search** and one short model call.
- The active model and search context are shown in the sidebar and Settings.

Web search is the largest cost, not the model. The app deliberately researches
only the prospects you choose.

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

Set your OpenAI API key once in the Windows environment:

```powershell
setx OPENAI_API_KEY "sk-..."
```

Then restart the app or terminal.

## Run

One-click (recommended):

- Double-click `launch_pr_agent_hidden.vbs` to start.
- Open `http://localhost:8501` if the browser does not open.
- Double-click `stop_pr_agent.bat` to stop.
- After an update, double-click `restart_pr_agent.vbs` to load the new code.

If you see an `ImportError` after changing files, the old app is still running.
Stop it and relaunch, or use `restart_pr_agent.vbs`.

From a shell:

```powershell
streamlit run app.py
```

## Brand configuration

The active brand, website, and product description are shown in **Settings**.
You can edit them there; they are saved to `data/brand_config.json`. Restart the
app to apply. Environment variables `BRAND_NAME`, `BRAND_DOMAIN`, and
`PRODUCT_DESCRIPTION` override the file.

The local `data/brand_config.json` file is private and gitignored, so you can use
the tool for a specific brand without changing the shareable defaults.

## Health check (one click)

Double-click `run_storage_check.vbs`. It runs the full storage test against a
temporary database, saves a record at every stage, restarts the session,
exercises outreach drafts, exports data, creates a backup, and verifies it.
It never touches the real research database and does not call the OpenAI API.
Details are written to `backups\latest_storage_check.txt`.

## Local data and backups

- Database: `data/pr_agent.sqlite3`
- Backups: `backups/`
- Data is **not synced** to other computers. Back up before updating or moving.
- Research Library → **Create database backup** creates a dated backup and
  verifies its integrity before reporting success.
- To restore, close the app and replace `data/pr_agent.sqlite3` with a backup.
  Keep a copy of the current file first.

## Safety rules

- The app never performs outreach.
- Contacts and policy findings are research, not permission or a guarantee.
- Approval only prepares the next step; it does not send anything.
- Always verify names, links, claims, and publisher rules before sending.
- Do not treat paid or affiliate placements as independent editorial endorsements.

## Project structure

- `app.py` - the three-page Streamlit workspace.
- `agent.py` - OpenAI Agents SDK prompts and structured output models.
- `database.py` - SQLite storage, migrations, CSVs, and verified backups.
- `storage_self_check.py` - end-to-end storage test.
- `run_storage_check.vbs` - one-click health check.
- `launch_pr_agent_hidden.vbs` - one-click launcher.
- `restart_pr_agent.vbs` - one-click restart after an update.
- `install_persistent_storage_update.vbs` - update installer with rollback.
- `README.txt` - short local user guide.

## Updating

Use `install_persistent_storage_update.vbs` only with a full update package
containing `agent.py`, `app.py`, and `database.py`. It stops the app, backs up
your code and database, installs the files, checks Python syntax and required
functions, and rolls back on failure.
