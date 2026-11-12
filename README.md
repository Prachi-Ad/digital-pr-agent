# digital-pr-agent

This repository was cleared on 2026-11-13 for a fresh start.

The previous tool (the Next.js app in `vercel-app/`, the Python research API, the local
Streamlit app, the Apps Script, and the handoff notes) is not gone: it is preserved in this
repository's history and on these two refs:

- branch `archive/session-2026-11-13`
- tag `session-archive-2026-11-13`

A full bundle of the repository as it was also exists outside the repo at:

    C:\Users\Prachi\vista-tool-archive-2026-11-13\repo-all-refs.bundle

Local-only data that was never in git (Streamlit `data/`, `backups/`, `.streamlit/`,
`vercel-app/.env.local`, the `.vercel` project link, and the old `*_backup_*.py` files)
was moved to the same archive folder.

## Restoring the old tool

```powershell
git checkout archive/session-2026-11-13
```

or, from the bundle:

```powershell
git clone C:\Users\Prachi\vista-tool-archive-2026-11-13\repo-all-refs.bundle restored
```
