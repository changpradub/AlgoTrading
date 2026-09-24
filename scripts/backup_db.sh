#!/usr/bin/env bash
# =============================================================================
# Automated PostgreSQL Daily Backup Script for Personal Algo-Trading Bot
# Retains backups for 30 days and removes older files.
# See UNIFIED_PLAN.md Section 5.
# =============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/var/backups/algotrading}"
DB_NAME="${DB_NAME:-algo_trading}"
DB_USER="${DB_USER:-algo_trader}"
DATE_STR=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/algo_trading_${DATE_STR}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting backup for database: ${DB_NAME}..."

# Execute pg_dump and pipe into gzip
if command -v pg_dump &> /dev/null; then
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup completed: ${BACKUP_FILE} ($(du -sh "${BACKUP_FILE}" | cut -f1))"
else
    echo "⚠️ pg_dump command not found. Aborting backup."
    exit 1
fi

# Clean up backups older than 30 days
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Cleaning up backups older than 30 days..."
find "${BACKUP_DIR}" -name "algo_trading_*.sql.gz" -type f -mtime +30 -exec rm -f {} \;
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup and cleanup cycle completed successfully."
