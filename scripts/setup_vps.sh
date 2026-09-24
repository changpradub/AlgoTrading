#!/usr/bin/env bash
# =============================================================================
# Automated VPS Provisioning & Setup Script for Personal Algo-Trading Bot
# Target OS: Ubuntu 22.04 / 24.04 LTS (Oracle Cloud Always Free or Standard VPS)
# =============================================================================

set -e

echo "============================================================"
echo " Starting Algo-Trading Bot VPS Setup (Ubuntu)"
echo "============================================================"

# Ensure script is run with sudo if needed
if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run this script with sudo: sudo bash scripts/setup_vps.sh"
  exit 1
fi

APP_USER="${SUDO_USER:-$USER}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "• Target User: ${APP_USER}"
echo "• Project Directory: ${APP_DIR}"

# 1. Update system packages
echo "--> 1. Updating APT repositories..."
apt-get update -y && apt-get upgrade -y

# 2. Install essential dependencies and Python 3
echo "--> 2. Installing System Utilities, Python 3, and build tools..."
apt-get install -y \
    curl \
    git \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libpq-dev \
    logrotate \
    cron \
    ufw \
    htop \
    jq

# 3. Install Node.js LTS and PM2
echo "--> 3. Installing Node.js LTS and PM2 Process Manager..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
npm install -g pm2

# 4. Install and configure PostgreSQL
echo "--> 4. Installing and configuring PostgreSQL..."
apt-get install -y postgresql postgresql-contrib
systemctl enable postgresql
systemctl start postgresql

# Create Database and User if not already present
DB_NAME="algo_trading"
DB_USER="algo_trader"
DB_PASS="AlgoTradingSecure2026!"

echo "Creating PostgreSQL user and database (${DB_NAME})..."
sudo -u postgres psql -c "DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;"

sudo -u postgres psql -c "SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

# 5. Setup Python Virtual Environment in Project Directory
echo "--> 5. Setting up Python Virtual Environment..."
cd "${APP_DIR}"

if [ ! -d ".venv" ]; then
    sudo -u "${APP_USER}" python3 -m venv .venv
fi

sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r requirements.txt

# Create logs directory
sudo -u "${APP_USER}" mkdir -p "${APP_DIR}/logs"
chmod 755 "${APP_DIR}/logs"

# 6. Setup Logrotate Configuration
echo "--> 6. Setting up Logrotate for application logs..."
cat <<EOF > /etc/logrotate.d/algotrading
${APP_DIR}/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 ${APP_USER} ${APP_USER}
    sharedscripts
}
EOF

# 7. Setup Daily Database Backup Cron Job
echo "--> 7. Setting up automated PostgreSQL daily backup cron..."
BACKUP_DIR="/var/backups/algotrading"
mkdir -p "${BACKUP_DIR}"
chown "${APP_USER}:${APP_USER}" "${BACKUP_DIR}"

chmod +x "${APP_DIR}/scripts/backup_db.sh"

CRON_CMD="0 5 * * * ${APP_DIR}/scripts/backup_db.sh >> ${APP_DIR}/logs/backup.log 2>&1"
(crontab -u "${APP_USER}" -l 2>/dev/null | grep -v "backup_db.sh" ; echo "${CRON_CMD}") | crontab -u "${APP_USER}" -

# 8. Configure PM2 Startup Hook
echo "--> 8. Configuring PM2 Startup..."
env PATH=$PATH:/usr/bin pm2 startup systemd -u "${APP_USER}" --hp "/home/${APP_USER}" || true

echo "============================================================"
echo " VPS Provisioning Complete!"
echo "============================================================"
echo "Next Steps:"
echo "1. Configure your production .env in ${APP_DIR}/.env"
echo "2. Run database migration:"
echo "   ${APP_DIR}/.venv/bin/python scripts/init_db.py"
echo "3. Start the bot with PM2:"
echo "   pm2 start ecosystem.config.js"
echo "   pm2 save"
echo "4. Monitor logs:"
echo "   pm2 logs algotrading-bot"
echo "============================================================"
