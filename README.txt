Vista Social PR Agent - Research Library and Storage Guide

WHAT THE APP DOES
- Turns published Vista Social articles into PR angles and editorial opportunities.
- Finds listicle, roundup, alternatives, and directory pages where Vista Social may fit.
- Researches publisher contacts and publisher inclusion policies for a human to review.
- Saves every listicle prospect, PR opportunity, journalist record, decision, contact finding, policy finding, and placement status in a local database.
- Never emails publishers, submits forms, or sends outreach automatically.

ONE-CLICK START
1. Double-click launch_vista_pr_agent_hidden.vbs.
2. Your browser opens the app at http://localhost:8501.
3. To stop the app, double-click stop_vista_pr_agent.bat.

CHECK THAT SAVING WORKS (ONE CLICK)
1. Double-click run_storage_check.vbs.
2. The check opens the real app against a temporary database, saves a prospect at every stage, restarts the session, exports the data, creates a backup, and checks the backup.
3. A message tells you whether every check passed.
4. Full details are written to backups\latest_storage_check.txt (and a dated copy).

The check never reads or changes your real research database. It is safe to run at any time.
It takes about 20-40 seconds and does not call the OpenAI API.

WHERE DATA IS STORED
- Main database: C:\Users\<your Windows user>\vista-pr-agent\data\vista_pr_agent.sqlite3
- Code and database backups: C:\Users\<your Windows user>\vista-pr-agent\backups\
- Storage check logs: backups\latest_storage_check.txt and backups\storage_check_<date>.txt

DATA BEHAVIOR
- Listicle prospects are keyed by normalized URL, so rerunning a search keeps their contact research, policy check, review decision, and placement progress.
- PR opportunities and journalist decisions are saved as soon as research finishes.
- Journalists are stored per person rather than per article, so co-authors on the same article remain separate records with independent decisions.
- Existing journalist records saved under the old article-only key are migrated automatically on the next launch.
- Contact research and publisher policy results are saved immediately when the research completes, not only when the page is closed.
- "Last updated" changes only when a record actually changes. Simply viewing a page no longer rewrites every timestamp.
- The active workspace snapshot is saved after each app run, so the current analysis and research results return after a restart.
- CSV exports are UTF-8 and protected against spreadsheet formula injection.
- Every database backup is checked with SQLite's integrity check before the app reports success.
- Data stays on this PC. It is not synced to other computers, so keep database backups somewhere safe.

BACKUP AND RESTORE
- Research Library > Create database backup creates a dated, verified backup.
- To restore, close the app and replace data\vista_pr_agent.sqlite3 with a backup file. Keep a copy of the current file first.
- Back up before installing updates or moving to another computer.

INSTALLING UPDATES
- Use install_persistent_storage_update.vbs only when you have a full update package containing agent.py, app.py, and database.py.
- The installer stops the app, backs up your current code and database, installs the files, and checks Python syntax and required functions. If a check fails, it restores the previous code.
- When the installer is run from inside the project folder, it now runs the checks without trying to copy files onto themselves.
- Older single-feature installers are kept in backups\legacy-installers and should not be used.

SAFETY
- Publisher research is informational and must be checked by a human.
- Policy findings are recommendations, not permission or a placement guarantee.
- The app does not contact publishers or send outreach. Human approval is required at every step.
