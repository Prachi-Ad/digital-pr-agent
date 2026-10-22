Digital PR Agent - Quick Guide

WHAT IT DOES
- Digital PR: published article -> PR angles -> editorial opportunities -> journalists -> outreach draft.
- Listicles: search -> prospects -> contacts and policy -> inclusion request.
- Saves every prospect, opportunity, journalist, contact, policy finding, draft, decision, and placement locally.
- Can send explicitly approved drafts in a confirmed Gmail batch from the local app. It never submits publisher forms. You approve every draft and confirm every batch.
- Vercel remains a non-sending demo.

ONE-CLICK START
1. Double-click launch_pr_agent_hidden.vbs.
2. Open http://localhost:8501 if the browser does not open.
3. To stop, double-click stop_pr_agent.bat.
4. After an update, double-click restart_pr_agent.vbs to load the new code.

THE THREE PAGES
- Workspace: the daily workflow. Pick Digital PR or Listicle inclusion and follow the numbered steps.
- Research Library: all saved records, email send history, CSV exports, and verified database backups.
- Settings: brand, sender details, Gmail SMTP, do-not-send list, model/cost information, storage, and safety rules.

DAILY WORKFLOW
Digital PR
1. Paste an article URL and analyze it.
2. Pick one PR angle.
3. Research opportunities and approve the strongest ones.
4. Research journalists and mark a qualified pitch target.
5. Prepare a draft, edit it, add the verified recipient email, and set its status to Approved for automated send. Then use the batch sender on the Outreach page and confirm. Or send it yourself outside the app.

Listicle inclusion
1. Search a category.
2. Review each prospect. Use the Needs review / Approved / All filter to focus the list. Set its status and placement progress, then run contact and policy research only for the ones worth pursuing.
3. Prepare an inclusion request for an approved prospect with a saved contact. Add the verified recipient email, approve it for automated send, and confirm the batch, or send/submit it yourself.

EMAIL SENDING (LOCAL ONLY)
1. Turn on 2-Step Verification for the Google account.
2. Create a Google app password at https://myaccount.google.com/apppasswords.
3. Settings > Email sending: enter the full Gmail / Google Workspace address and the app password. Set delay (default 30 seconds), daily cap (default 20), and mailing address. Click Test SMTP connection.
4. Draft status must be Approved for automated send. Batch sending also requires a separate confirmation checkbox.
5. Every email gets an opt-out line. All attempts are in Research Library > Email send log.
6. If someone opts out, add their address to Settings > Do-not-send list before any further batch.
- Credentials are stored in data\email_config.json (gitignored, plaintext app password). Protect the computer.
- Sending is sequential, with a delay and daily cap. There is no scheduler or unattended sending.

SAVING AND BACKUPS
- Database: project folder\data\pr_agent.sqlite3
- Email credentials: project folder\data\email_config.json (gitignored)
- Backups: project folder\backups\
- Research Library > Create database backup makes a dated, verified backup.
- Data does not sync to other computers. Keep backups somewhere safe.
- To restore, close the app and replace data\pr_agent.sqlite3 with a backup. Keep a copy of the current file first.

CHECK THAT SAVING WORKS (ONE CLICK)
1. Double-click run_storage_check.vbs.
2. It uses a temporary database and never touches your real research.
3. It takes about 20-40 seconds, does not call the OpenAI API, and does not send email.
4. Full details: backups\latest_storage_check.txt.

COST CONTROLS
- Default model: gpt-5-nano.
- Default web search context: low.
- Agent turns: 3.
- Contact, policy, and journalist research run only when you click their buttons.
- Outreach drafts use no web search.
- The active model is shown in the sidebar and Settings.

BRAND AND SENDER
- Settings > Brand saves data\brand_config.json. Restart the app to apply.
- Sender identity is fixed as Prachi, SEO Specialist in every draft and outgoing email.
- Environment variables BRAND_NAME and PRODUCT_DESCRIPTION override the saved file.

SAFETY
- Sending requires Approved for automated send plus a separate batch confirmation. Approval alone does not send.
- Use only relevant, publicly listed editorial contacts. Do not send to purchased lists.
- Every email gets an opt-out line. Add anyone who opts out to the do-not-send list before any further batch.
- Publisher research and policy findings are recommendations, not permission.
- Paid or affiliate placements are labelled clearly.
- Always verify names, links, claims, and publisher rules before sending.
- The app never submits publisher forms or sends on a schedule.

INSTALLING UPDATES
- Use install_persistent_storage_update.vbs only with a full update package containing agent.py, app.py, database.py, and email_sender.py.
- It backs up your code and database, checks syntax and required functions (including the email sender), and rolls back on failure.
- After any update, double-click restart_pr_agent.vbs. If the browser shows an ImportError, the old app was still running; restart it.
