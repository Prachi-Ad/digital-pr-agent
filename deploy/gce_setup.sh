#!/usr/bin/env bash
# Install the PR Agent on a fresh Ubuntu VM with Docker + Caddy.
# Run as root:
#   sudo bash /tmp/gce_setup.sh /tmp/pr-agent.zip
set -euo pipefail

APP_DIR="/opt/pr-agent"
DATA_DIR="$APP_DIR/data"
ZIP="${1:-/tmp/pr-agent.zip}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo."
  exit 1
fi
if [ ! -f "$ZIP" ]; then
  echo "Upload the deployment zip to $ZIP first."
  exit 1
fi

apt-get update
apt-get install -y docker.io unzip curl gnupg
systemctl enable --now docker

mkdir -p "$APP_DIR/app" "$DATA_DIR"
rm -rf "$APP_DIR/app"
mkdir -p "$APP_DIR/app"
unzip -o "$ZIP" -d "$APP_DIR/app"

if [ ! -f "$APP_DIR/.env" ]; then
  echo
  echo "Set the app secrets. They are stored only on this VM."
  read -r -p "OpenAI API key: " OPENAI_API_KEY
  read -r -s -p "Workspace password for the login gate: " APP_PASSWORD
  echo
  cat > "$APP_DIR/.env" <<EOF
OPENAI_API_KEY=$OPENAI_API_KEY
APP_PASSWORD=$APP_PASSWORD
PR_AGENT_DATA_DIR=/data
BRAND_NAME=Vista Social
BRAND_DOMAIN=https://vistasocial.com
PRODUCT_DESCRIPTION=a social media management platform for agencies, brands, and social media teams
GOOGLE_OAUTH_REDIRECT_URI=https://pr.prachiadmane.com/
EOF
  chmod 600 "$APP_DIR/.env"
fi

docker build -t pr-agent "$APP_DIR/app"
docker rm -f pr-agent >/dev/null 2>&1 || true
docker run -d \
  --name pr-agent \
  --restart unless-stopped \
  --env-file "$APP_DIR/.env" \
  -v "$DATA_DIR:/data" \
  -p 127.0.0.1:8501:8501 \
  pr-agent

if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

cat > /etc/caddy/Caddyfile <<'EOF'
pr.prachiadmane.com {
    reverse_proxy 127.0.0.1:8501
}
EOF
systemctl enable caddy
systemctl restart caddy

echo
echo "Done."
echo "1. Point pr.prachiadmane.com (Cloudflare DNS, proxy off) at this VM's external IP."
echo "2. Wait for Caddy to issue HTTPS, then open https://pr.prachiadmane.com/."
echo "3. Add https://pr.prachiadmane.com/ to the Google OAuth client redirect URIs."
