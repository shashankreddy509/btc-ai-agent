#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install_service.sh  —  Run on EC2 after code is synced to install/restart
#                         the systemd service.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$HOME/btc-ai-agent"
SERVICE_NAME="btc-agent"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
UV_BIN="$HOME/.local/bin/uv"

# Verify .env exists
if [ ! -f "$APP_DIR/.env" ]; then
    echo "❌  $APP_DIR/.env not found."
    echo "    Copy and fill in your credentials first:"
    echo "      cp $APP_DIR/.env.example $APP_DIR/.env && nano $APP_DIR/.env"
    exit 1
fi

echo "==> Installing Python dependencies..."
cd "$APP_DIR"
"$UV_BIN" sync

echo "==> Writing systemd service to $SERVICE_FILE..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=BTC AI Agent (scanner + morning briefing)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$UV_BIN run python main.py all --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
# Give the process access to the .env file
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling and starting $SERVICE_NAME..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "✅ Service deployed. Useful commands:"
echo "   Logs (live):  sudo journalctl -u $SERVICE_NAME -f"
echo "   Status:       sudo systemctl status $SERVICE_NAME"
echo "   Restart:      sudo systemctl restart $SERVICE_NAME"
echo "   Stop:         sudo systemctl stop $SERVICE_NAME"
