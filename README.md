# Digital PR Agent

A local Streamlit workspace for **Digital PR** and **listicle prospecting**.
It turns published articles into PR angles, finds editorial and listicle
opportunities, researches contacts and publisher policies, prepares outreach
drafts for human review, and stores every record locally.

From the local app, you can also send explicitly approved drafts through
**Gmail / Google Workspace** or a **custom SMTP mailbox** in a confirmed batch,
using either **Google Workspace sign-in (OAuth)**, a **Google app password**, or
a **designated sending email with SMTP login**, with a delay, a daily cap, a
do-not-send list, and a permanent send log. **The app never submits a
publisher form.** You approve every draft and confirm every batch before a
message leaves your computer. Vercel remains a non-sending demo.

## The simple workflow

The app has three pages:

1. **Workspace** - the daily workflow. Choose one of two paths:
   - **Digital PR:** article → PR angles → opportunities → journalists → outreach draft.
   - **Listicle inclusion:** search → prospects, contacts, and policy → inclusion request.
2. **Research Library** - saved prospects, PR opportunities, journalists, drafts,
   email send history, CSV exports, and verified database backups.
3. **Settings** - brand, sender details, email sending (OAuth, app password, or
   custom SMTP), do-not-send list, model/cost information, storage, safety.

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
  research. Drafts are editable and tracked as Draft, Approved for automated
  send, Approved for manual send, Sent, Send failed, Sent manually, Replied,
  Placement confirmed, Declined, or Do not send.
- **Batch sending:** approved drafts can be sent through Gmail / Google
  Workspace from the Outreach page after a separate confirmation. Every email
  gets an opt-out line and is recorded in the send log.
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

## Email sending (local only)

Sending is optional and works only in the local Streamlit app. Vercel cannot
send email. In **Settings -> Email sending**, choose either **Google Workspace
sign-in (OAuth)** or **Google app password**.

### Option A: Google Workspace sign-in (OAuth)

Use this for a work or school Google account when the Workspace admin has
blocked app passwords. It is the same kind of Google connection that tools such
as Instantly and ContactOut show, but this local app needs its own OAuth client.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or
   select a project **inside your Google Workspace organization**.
2. Open **APIs & Services -> OAuth consent screen** (the console may call this
   **Google Auth Platform**). Choose **Internal** for a Workspace account.
   - If you cannot use Internal, choose **External**, put the app in testing
     mode, and add your work email as a test user. Google expires testing-mode
     refresh tokens after 7 days, so you will need to reconnect.
3. Add these scopes: `openid`, `email`, and `https://mail.google.com/`.
4. Open **Credentials -> Create credentials -> OAuth client ID -> Web
   application**.
5. Under **Authorized redirect URIs**, add exactly:
   `http://localhost:8501/`
6. In Settings, select **Google Workspace sign-in (OAuth)**, paste the client ID
   and client secret, and click **Save OAuth settings**.
7. Click **Connect Google Workspace account**, sign in with the work account,
   and approve access. Then click **Test Google sign-in**.
8. In a draft, add a verified recipient email and set the status to
   **Approved for automated send**. On the Outreach page, review the batch, tick
   the confirmation checkbox, and click **Send ... approved emails**.

Important Workspace caveats:

- A custom local app cannot reuse Instantly's or ContactOut's OAuth client. Your
  Google Cloud project and OAuth client are your own.
- A Workspace admin may need to allow this OAuth app and the Gmail scope. If the
  admin blocks it, the app cannot bypass that; ask the admin to allow the client
  ID or use another approved sending method.
- Gmail SMTP over OAuth requires the broad `https://mail.google.com/` scope.
  The app uses it only to log in and send; it does not read mail. If your admin
  will not approve that scope, ask them to enable app passwords for your user or
  use an approved SMTP provider.
- Use **Internal** rather than **External testing** for a durable connection.
  Testing-mode refresh tokens expire after 7 days.
- The OAuth client secret and refresh token are stored locally in
  `data/email_config.json` (gitignored). Revoke the app's access in your Google
  Account permissions if the file is exposed.

### Option B: Google app password

1. Turn on 2-Step Verification for the Google account.
2. Create a Google **app password** at
   `https://myaccount.google.com/apppasswords`.
3. In **Settings -> Email sending**, select **Google app password**, enter the
   full Gmail / Google Workspace address and the app password. Set the delay
   (default 30 seconds), daily cap (default 20), and optional mailing address.
   Click **Test SMTP connection**.
4. In a draft, add a verified recipient email and set the status to
   **Approved for automated send**.
5. On the Outreach page, review the batch, tick the confirmation checkbox, and
   click **Send ... approved emails**.

If Google shows "The setting you are looking for is not available for your
account" at the app-password page, the Workspace admin has disabled app
passwords for your user. Use OAuth, ask the admin to enable app passwords, or
use an approved SMTP provider.

### Option C: Custom SMTP / designated email

Use this when you have a dedicated sending mailbox from your email host or an
SMTP service, and the provider gives you SMTP login details. The app sends as
the From address you enter.

1. In Settings, select **Custom SMTP / designated email**.
2. Enter the **designated From email address**.
3. Enter the provider's **SMTP host**, **SMTP port**, connection security
   (STARTTLS is usually port 587; SSL/TLS is usually port 465), **SMTP
   username**, and **SMTP password** or API key.
4. Click **Save custom SMTP settings**, then **Test custom SMTP connection**.
5. Approve a draft and run a one-recipient batch as usual.

The provider must allow the From address or its domain. If you want to send
from a Google Workspace address, Google normally requires OAuth or an
admin-approved SMTP relay; a normal Google password or an unapproved SMTP
connection will not work. If you do not have SMTP credentials for the mailbox,
ask the provider or your Workspace admin, or use a sending service such as
Resend, SendGrid, Mailgun, Postmark, Brevo, or SMTP2GO after verifying the
sending domain.

### Shared sending safeguards

The app sends one recipient at a time. It never sends on a schedule or without
the confirmation checkbox. Every email includes an opt-out line and
`List-Unsubscribe` header. All attempts are logged in
**Research Library -> Email send log**.

If someone asks not to be contacted, add their address to the **do-not-send
list** in Settings. Matching drafts are blocked from future batches.

Credentials live in `data/email_config.json`, which is gitignored and never
committed. The file can contain an app password, OAuth client secret, and
refresh token in plaintext, so protect the computer and revoke/rotate them if
the file is exposed.

The local launchers bind Streamlit to `127.0.0.1` so other devices on your
network cannot reach the sending UI. Keep the tab open while a batch runs.

## Requirements

- Windows (the one-click launchers are `.vbs` / `.bat`)
- Python 3.11+ (tested on 3.14.7)
- An OpenAI API key with access to a nano model
- Optional for sending: a Gmail / Google Workspace account, plus either a
  Google Workspace OAuth client or a Google app password, or a custom SMTP
  mailbox with a designated From address and SMTP login

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
It never touches the real research database, does not call the OpenAI API, and
does not send email. Details are written to `backups\latest_storage_check.txt`.

## Local data and backups

- Database: `data/pr_agent.sqlite3`
- Email credentials: `data/email_config.json` (gitignored; may contain an app
  password, SMTP password, OAuth client secret, and refresh token in plaintext)
- Backups: `backups/`
- Data is **not synced** to other computers. Back up before updating or moving.
- Research Library → **Create database backup** creates a dated backup and
  verifies its integrity before reporting success.
- To restore, close the app and replace `data/pr_agent.sqlite3` with a backup.
  Keep a copy of the current file first.

## Safety rules

- Sending requires a draft status of **Approved for automated send** plus a
  separate batch confirmation. Approval alone does not send.
- The app sends only from the local app, one recipient at a time, with a delay
  and a daily cap. It never sends on a schedule.
- Use only relevant, publicly listed editorial contacts. Do not send to
  purchased lists.
- Every email gets an opt-out line. Add anyone who opts out to the do-not-send
  list before any further batch.
- Contacts and policy findings are research, not permission or a guarantee.
- Always verify names, links, claims, and publisher rules before sending.
- Do not treat paid or affiliate placements as independent editorial endorsements.

## Project structure

- `app.py` - the three-page Streamlit workspace.
- `agent.py` - OpenAI Agents SDK prompts and structured output models.
- `database.py` - SQLite storage, migrations, CSVs, send log, and verified backups.
- `email_sender.py` - local SMTP/OAuth config, Google OAuth/XOAUTH2, custom
  SMTP, message building, and sending.
- `storage_self_check.py` - end-to-end storage test.
- `run_storage_check.vbs` - one-click health check.
- `launch_pr_agent_hidden.vbs` - one-click launcher.
- `restart_pr_agent.vbs` - one-click restart after an update.
- `install_persistent_storage_update.vbs` - update installer with rollback.
- `vercel-app/` - public Next.js research demo; no persistence and no sending.
- `README.txt` - short local user guide.

## Updating

Use `install_persistent_storage_update.vbs` only with a full update package
containing `agent.py`, `app.py`, `database.py`, and `email_sender.py`. It stops
the app, backs up your code and database, installs the files, checks Python
syntax and required functions (including the email sender), and rolls back on
failure.

## Public demo (Vercel)

- URL: `https://pr.prachiadmane.com/`
- The demo is research-only. It never sends email and never collects email
  credentials.
- `/api/analyze` requires a short-lived HMAC bearer token minted by
  `/api/token`. Tokens are issued only to allowed demo origins and expire after
  five minutes.
- Per-IP limits: 12 research calls per 10 minutes and 60 per day. A
  per-instance daily budget of 200 calls is the last backstop.
- Required environment variable in Vercel (Production, Preview, Development):
  `DEMO_SIGNING_SECRET`, at least 32 characters. Generate one with
  `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`.
  Without it the API returns 503 instead of running.
- Optional overrides: `DEMO_IP_REQUESTS_PER_10_MIN`,
  `DEMO_IP_REQUESTS_PER_DAY`, `DEMO_DAILY_REQUEST_CAP`.
- Deploy from the repository root, because the Vercel project root directory is
  `vercel-app`:

```powershell
vercel --prod --yes --project vercel-app --scope prachi-8a13
```

