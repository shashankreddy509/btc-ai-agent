#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ec2_setup.sh  —  Run ONCE on a fresh Ubuntu 22.04 / 24.04 EC2 instance
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$HOME/btc-ai-agent"

echo "==> Updating system packages..."
sudo apt-get update -q && sudo apt-get upgrade -y -q

echo "==> Installing system dependencies..."
sudo apt-get install -y -q \
    git curl unzip \
    python3 python3-pip python3-venv \
    build-essential

echo "==> Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

echo "==> Creating app directory: $APP_DIR"
mkdir -p "$APP_DIR"

echo ""
echo "✅ EC2 base setup complete."
echo ""
echo "Next steps:"
echo "  1. Run deploy.sh from your Mac to push the code"
echo "  2. SSH in and run:  cd $APP_DIR && cp .env.example .env && nano .env"
echo "  3. Then run:  bash deploy/install_service.sh"
