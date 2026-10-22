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
- Settings: brand, sender details, email sending (Google Workspace OAuth, app password, or custom SMTP), do-not-send list, model/cost information, storage, and safety rules.

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
Choose one of two Google connection methods in Settings > Email sending.

OPTION A - GOOGLE WORKSPACE SIGN-IN (OAUTH)
Use this for a work/school account when app passwords are blocked.
1. Create a Google Cloud project inside your Workspace organization.
2. Configure the OAuth consent screen. Choose Internal for a durable Workspace connection. External testing works, but Google expires refresh tokens after 7 days.
3. Add scopes: openid, email, https://mail.google.com/
4. Create an OAuth client ID of type Web application. Add this authorized redirect URI exactly: http://localhost:8501/
5. Settings > Email sending > Google Workspace sign-in (OAuth): paste the client ID and secret, save, then click Connect Google Workspace account.
6. Sign in with the work account and approve. Click Test Google sign-in.
- A custom local app cannot reuse Instantly's or ContactOut's OAuth client. You need your own Google Cloud OAuth client.
- A Workspace admin may need to allow this OAuth app and the Gmail scope. The app cannot bypass an admin block. Ask the admin to allow the client ID or enable app passwords.
- Gmail SMTP over OAuth requires the broad https://mail.google.com/ scope. The app only logs in and sends; it does not read mail.
- If the admin will not approve the scope, ask them to enable app passwords for your user or use an approved SMTP provider.

OPTION B - GOOGLE APP PASSWORD
1. Turn on 2-Step Verification for the Google account.
2. Create a Google app password at https://myaccount.google.com/apppasswords.
3. Settings > Email sending > Google app password: enter the full Gmail / Google Workspace address and the app password. Set delay (default 30 seconds), daily cap (default 20), and mailing address. Click Test SMTP connection.
- If Google says the setting is not available for your account, the Workspace admin has disabled app passwords. Use OAuth or ask the admin.

OPTION C - CUSTOM SMTP / DESIGNATED EMAIL
1. Settings > Email sending > Custom SMTP / designated email.
2. Enter the designated From email address and the SMTP host, port, connection security (STARTTLS usually 587, SSL/TLS usually 465), username, and password or API key from your email host or SMTP service.
3. Save custom SMTP settings, then Test custom SMTP connection.
- The provider must allow the From address or its domain. If the mailbox is Google Workspace, Google normally requires OAuth or an admin-approved SMTP relay; a normal Google password will not work.
- If you do not have SMTP credentials, ask the provider or Workspace admin, or use a sending service such as Resend, SendGrid, Mailgun, Postmark, Brevo, or SMTP2GO after verifying the sending domain.

ALL METHODS
1. Draft status must be Approved for automated send. Batch sending also requires a separate confirmation checkbox.
2. Every email gets an opt-out line. All attempts are in Research Library > Email send log.
3. If someone opts out, add their address to Settings > Do-not-send list before any further batch.
- Credentials are stored in data\email_config.json (gitignored; may contain an app password, SMTP password, OAuth client secret, and refresh token in plaintext). Protect the computer.
- Sending is sequential, with a delay and daily cap. There is no scheduler or unattended sending. Keep the tab open while a batch runs.
- The local launchers bind the app to 127.0.0.1 so other devices on your network cannot reach the sending UI.

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
