#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh  —  Run from your Mac to push code to EC2 and restart the service.
#
# Usage:
#   ./deploy/deploy.sh <EC2_HOST> [<KEY_FILE>]
#
# Examples:
#   ./deploy/deploy.sh ubuntu@ec2-1-2-3-4.compute.amazonaws.com ~/.ssh/my-key.pem
#   ./deploy/deploy.sh ubuntu@1.2.3.4                           # if key is in ssh-agent
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

EC2_HOST="${1:-}"
KEY_FILE="${2:-}"

if [ -z "$EC2_HOST" ]; then
    echo "Usage: $0 <user@ec2-host> [/path/to/key.pem]"
    exit 1
fi

SSH_OPTS="-o StrictHostKeyChecking=no"
RSYNC_SSH="ssh -o StrictHostKeyChecking=no"
if [ -n "$KEY_FILE" ]; then
    SSH_OPTS="$SSH_OPTS -i $KEY_FILE"
    RSYNC_SSH="$RSYNC_SSH -i $KEY_FILE"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"   # repo root
REMOTE_DIR="~/btc-ai-agent"

echo "==> Syncing code to $EC2_HOST:$REMOTE_DIR ..."
rsync -az --progress \
    -e "$RSYNC_SSH" \
    --exclude='.venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='data/' \
    --exclude='tasks/' \
    --exclude='debug_tf.py' \
    "$APP_DIR/" \
    "$EC2_HOST:$REMOTE_DIR/"

echo "==> Installing deps and restarting service on EC2..."
# shellcheck disable=SC2087
ssh $SSH_OPTS "$EC2_HOST" bash <<'REMOTE'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd ~/btc-ai-agent
uv sync --quiet
if systemctl is-active --quiet btc-agent; then
    sudo systemctl restart btc-agent
    echo "✅ btc-agent restarted."
    # Restart the collector unit too if it has been installed.
    if systemctl list-unit-files | grep -q '^btc-liquidity\.service'; then
        sudo systemctl restart btc-liquidity
        echo "✅ btc-liquidity restarted."
    else
        echo "ℹ️  btc-liquidity unit not installed yet. Run deploy/install_service.sh on EC2 to split the collector out."
    fi
else
    echo "ℹ️  Service not running yet. Run deploy/install_service.sh on EC2 first."
fi
REMOTE

echo ""
echo "✅ Deploy complete!"
echo "   Live logs:  ssh $SSH_OPTS $EC2_HOST 'sudo journalctl -u btc-agent -f'"
