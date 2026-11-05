# Put the full tool at https://pr.prachiadmane.com/

Vercel cannot run this app: no persistent disk, SMTP blocked, no long-running
process. The domain can still stay the same — point it at a small VM that runs
the container.

**Free option: Google Cloud e2-micro**
The always-free tier includes one e2-micro VM and a 30 GB disk in
`us-central1`, `us-west1`, or `us-east1`. You need a billing account (card) even
for the free tier; normal use stays within the free allowance.

## 1. Create the VM

In Google Cloud Console → Compute Engine → **Create instance**:

- Name: `pr-agent`
- Region: `us-central1` (or `us-west1` / `us-east1`)
- Machine type: **e2-micro**
- Boot disk: **Ubuntu 24.04 LTS**, 30 GB standard persistent disk
- Firewall: allow **HTTP** and **HTTPS**
- Create.

Then open **SSH** (browser) for the VM.

## 2. Upload the app

The deployment zip is on your computer:

```
deploy/pr-agent-deploy.zip
```

In the browser SSH window: gear icon → **Upload file** → choose that zip.
It lands in your home folder (usually `/home/USERNAME/`).

## 3. Install

In the SSH terminal:

```bash
sudo apt-get update && sudo apt-get install -y unzip
mkdir -p /tmp/pr-deploy
unzip -o ~/pr-agent-deploy.zip -d /tmp/pr-deploy
sudo bash /tmp/pr-deploy/deploy/gce_setup.sh ~/pr-agent-deploy.zip
```

The script installs Docker and Caddy, builds the image, starts the app on
`127.0.0.1:8501`, and configures HTTPS for `pr.prachiadmane.com`. It prompts for
your OpenAI key and a workspace password.

## 4. Point the domain here

1. Compute Engine → VM → note the **external IP**.
2. Cloudflare → DNS → `pr` record → edit:
   - Type: `A`
   - Name: `pr`
   - Content: the VM IP
   - Proxy: **DNS only** (grey cloud) until the certificate is issued.
3. Caddy requests the certificate automatically. Open
   `https://pr.prachiadmane.com/` after a minute.

The Vercel deployment stays available at its `vercel.app` URL. Move the demo to
`demo.prachiadmane.com` later if you want to keep it.

## 5. Google OAuth

In Google Cloud → Credentials → your OAuth client, add:

```
https://pr.prachiadmane.com/
```

In the app: Settings → Sending method → **Sign in with Google (OAuth)** → save
client ID/secret → **Connect another Google account** for each account.

## 6. Data

The database and settings live on the VM disk at `/opt/pr-agent/data`.
Back up from Settings, or snapshot the disk in Compute Engine.

To migrate the local database, from the SSH session:

```bash
sudo systemctl stop docker
sudo cp /opt/pr-agent/data/pr_agent.sqlite3 /opt/pr-agent/data/backup.sqlite3
# upload data/pr_agent.sqlite3 from your computer through the SSH upload button,
# then move it to /opt/pr-agent/data/
sudo systemctl start docker
```

## Paid alternative: Fly.io

`fly.toml` and `Dockerfile` are ready. Fly is ~$5/month, allows SMTP, and is
less manual than a VM. See the earlier Fly steps if you prefer it.

## Notes

- The login gate turns on when `APP_PASSWORD` is set.
- Gmail sends over port 587. Google Cloud blocks port 25 only, so 587 works.
- Do not put OpenAI/Google/Hunter/ContactOut keys in the Vercel project.
