#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install_service.sh  —  Run on EC2 after code is synced to install/restart
#                         the systemd services.
#
# Installs TWO units:
#   btc-agent.service      → web dashboard + scheduler (uvicorn). No browser.
#   btc-liquidity.service  → CoinGlass Playwright collector, CPU/memory-capped
#                            so headless Chromium can never starve the API.
#
# Why split: on a 2-vCPU t3.medium, the in-process Chromium scrape grabbed both
# cores for 60-90s every cycle and made the API crawl. Running it as its own
# cgroup-bounded unit caps it at a fraction of one core and deprioritizes it.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$HOME/btc-ai-agent"
SERVICE_NAME="btc-agent"
LIQ_SERVICE_NAME="btc-liquidity"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LIQ_SERVICE_FILE="/etc/systemd/system/${LIQ_SERVICE_NAME}.service"
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
# Chromium for the liquidity collector (no-op if already present)
"$UV_BIN" run playwright install chromium

echo "==> Writing $SERVICE_FILE (web + scheduler, no browser)..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=BTC AI Agent (scanner + morning briefing + web)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
# Collector runs in its own unit (btc-liquidity) — never in the web process.
Environment=LIQUIDITY_ENABLED=false
ExecStart=$UV_BIN run python main.py all --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "==> Writing $LIQ_SERVICE_FILE (Playwright collector, CPU/memory-capped)..."
sudo tee "$LIQ_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=BTC AI Agent — CoinGlass liquidity collector (Playwright/Chromium)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
# Scrape every 30 min instead of 15 — halves the burst frequency.
Environment=LIQUIDITY_INTERVAL_MIN=30
ExecStart=$UV_BIN run liquidity-collect
# ── Resource caps: keep Chromium off the cores uvicorn needs ──
# 60% of ONE core (box has 2 vCPU → API always has ~1.4 cores free).
CPUQuota=60%
MemoryMax=900M
Nice=15
IOSchedulingClass=idle
Restart=on-failure
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling and (re)starting both services..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" "$LIQ_SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME" "$LIQ_SERVICE_NAME"

sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager || true
sudo systemctl status "$LIQ_SERVICE_NAME" --no-pager || true

echo ""
echo "✅ Services deployed. Useful commands:"
echo "   App logs:        sudo journalctl -u $SERVICE_NAME -f"
echo "   Collector logs:  sudo journalctl -u $LIQ_SERVICE_NAME -f"
echo "   Collector CPU:   systemctl show $LIQ_SERVICE_NAME -p CPUQuotaPerSecUSec,MemoryMax"
echo "   Restart app:     sudo systemctl restart $SERVICE_NAME"
echo "   Restart collect: sudo systemctl restart $LIQ_SERVICE_NAME"
