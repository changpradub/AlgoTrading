#!/usr/bin/env bash
# =============================================================================
# Automated Deployment Script for Ubuntu VPS
# Pulls latest branch changes, updates dependencies, runs DB migrations, and reloads PM2
# Usage: ./scripts/deploy.sh [develop|main]
# =============================================================================

set -e

BRANCH="${1:-develop}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "============================================================"
echo " Deploying Personal Algo-Trading Bot (Branch: ${BRANCH})"
echo "============================================================"

cd "${APP_DIR}"

# 1. Fetch & checkout branch
echo "--> 1. Fetching latest Git updates..."
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

# 2. Update Python dependencies
echo "--> 2. Updating virtual environment dependencies..."
if [ -d ".venv" ]; then
    ./.venv/bin/pip install --upgrade pip
    ./.venv/bin/pip install -r requirements.txt
else
    echo "⚠️ .venv not found. Please run scripts/setup_vps.sh first."
    exit 1
fi

# 3. Run database migrations
echo "--> 3. Checking & executing database migrations..."
./.venv/bin/python scripts/init_db.py

# 4. Reload PM2 Process
echo "--> 4. Reloading bot process via PM2..."
if command -v pm2 &> /dev/null; then
    pm2 reload ecosystem.config.js || pm2 start ecosystem.config.js
    pm2 save
    echo "✅ PM2 process reloaded."
else
    echo "⚠️ PM2 not found. Please install PM2 or start manually."
fi

echo "============================================================"
echo " Deployment to ${BRANCH} Completed Successfully!"
echo "============================================================"
