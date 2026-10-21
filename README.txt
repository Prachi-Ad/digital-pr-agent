Digital PR Agent - Quick Guide

WHAT IT DOES
- Digital PR: published article -> PR angles -> editorial opportunities -> journalists -> outreach draft.
- Listicles: search -> prospects -> contacts and policy -> inclusion request.
- Saves every prospect, opportunity, journalist, contact, policy finding, draft, decision, and placement locally.
- Never sends email, submits forms, or contacts anyone. You approve every send.

ONE-CLICK START
1. Double-click launch_pr_agent_hidden.vbs.
2. Open http://localhost:8501 if the browser does not open.
3. To stop, double-click stop_pr_agent.bat.
4. After an update, double-click restart_pr_agent.vbs to load the new code.

THE THREE PAGES
- Workspace: the daily workflow. Pick Digital PR or Listicle inclusion and follow the numbered steps.
- Research Library: all saved records, CSV exports, and verified database backups.
- Settings: brand, sender details, model/cost information, storage, and safety rules.

DAILY WORKFLOW
Digital PR
1. Paste an article URL and analyze it.
2. Pick one PR angle.
3. Research opportunities and approve the strongest ones.
4. Research journalists and mark a qualified pitch target.
5. Prepare a draft, edit it, and mark your own status. Send it yourself outside the app.

Listicle inclusion
1. Search a category.
2. Review each prospect. Use the Needs review / Approved / All filter to focus the list. Set its status and placement progress, then run contact and policy research only for the ones worth pursuing.
3. Prepare an inclusion request for an approved prospect with a saved contact. Send or submit it yourself.

SAVING AND BACKUPS
- Database: project folder\data\pr_agent.sqlite3
- Backups: project folder\backups\
- Research Library > Create database backup makes a dated, verified backup.
- Data does not sync to other computers. Keep backups somewhere safe.
- To restore, close the app and replace data\pr_agent.sqlite3 with a backup. Keep a copy of the current file first.

CHECK THAT SAVING WORKS (ONE CLICK)
1. Double-click run_storage_check.vbs.
2. It uses a temporary database and never touches your real research.
3. It takes about 20-40 seconds and does not call the OpenAI API.
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
- Settings > Your sender details fills your name and role into draft placeholders.
- Environment variables BRAND_NAME and PRODUCT_DESCRIPTION override the saved file.

SAFETY
- Publisher research and policy findings are recommendations, not permission.
- Paid or affiliate placements are labelled clearly.
- Always verify names, links, claims, and publisher rules before sending.
- The app never performs outreach.

INSTALLING UPDATES
- Use install_persistent_storage_update.vbs only with a full update package containing agent.py, app.py, and database.py.
- It backs up your code and database, checks syntax and required functions, and rolls back on failure.
- After any update, double-click restart_pr_agent.vbs. If the browser shows an ImportError, the old app was still running; restart it.
