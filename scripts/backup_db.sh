#!/bin/bash
# Database backup script with rotation
# Automatically backs up PostgreSQL/TimescaleDB and manages backup retention
# Add to crontab: 0 2 * * * /path/to/backup_db.sh (2 AM daily)

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:=/home/$(whoami)/trading-bot/backups}"
DB_CONTAINER="${DB_CONTAINER:=trading-db}"
DB_USER="${DB_USER:=trading}"
DB_NAME="${DB_NAME:=trading_db}"

# Retention policy
DAILY_RETENTION=7      # Keep 7 daily backups
WEEKLY_RETENTION=4     # Keep 4 weekly backups
COMPRESS_METHOD="gzip" # Use gzip compression

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Helper functions
log_info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR${NC} $1"
}

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    log_info "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
fi

# Check if Docker container is running
if ! docker ps | grep -q "$DB_CONTAINER"; then
    log_error "Database container '$DB_CONTAINER' is not running"
    exit 1
fi

# Generate backup filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql"
BACKUP_COMPRESSED="${BACKUP_FILE}.gz"

log_info "Starting database backup..."
log_info "Database: $DB_NAME"
log_info "Container: $DB_CONTAINER"
log_info "Output: $BACKUP_COMPRESSED"

# Perform backup using docker exec
if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" > "$BACKUP_FILE"; then
    log_success "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

    # Compress backup
    log_info "Compressing backup..."
    if gzip -9 "$BACKUP_FILE"; then
        log_success "Backup compressed: $BACKUP_COMPRESSED ($(du -h "$BACKUP_COMPRESSED" | cut -f1))"
        # Remove uncompressed file
        rm -f "$BACKUP_FILE"
    else
        log_error "Failed to compress backup"
        exit 1
    fi
else
    log_error "Failed to create backup"
    exit 1
fi

# Rotate old backups based on retention policy
log_info "Rotating old backups..."

# Find and delete old daily backups
DAILY_FILES=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -type f | sort -r | tail -n +$((DAILY_RETENTION + 1)))
if [ -n "$DAILY_FILES" ]; then
    log_info "Removing old daily backups..."
    echo "$DAILY_FILES" | while read -r file; do
        log_info "Deleting: $(basename "$file") ($(du -h "$file" | cut -f1))"
        rm -f "$file"
    done
fi

# List current backups
log_info "Current backups:"
ls -lh "$BACKUP_DIR" | tail -n +2 | awk '{print "  " $9 " (" $5 ")"}'

# Calculate backup directory size
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log_success "Backup complete. Total backup storage: $TOTAL_SIZE"

# Optional: Verify backup integrity
log_info "Verifying backup integrity..."
if gzip -t "$BACKUP_COMPRESSED" 2>/dev/null; then
    log_success "Backup integrity verified"
else
    log_error "Backup integrity check failed"
    exit 1
fi

# Optional: Upload to remote storage (uncomment if needed)
# log_info "Uploading backup to remote storage..."
# aws s3 cp "$BACKUP_COMPRESSED" "s3://your-bucket/backups/" --region us-ashburn-1
# if [ $? -eq 0 ]; then
#     log_success "Backup uploaded to S3"
# else
#     log_error "Failed to upload backup to S3"
# fi

exit 0
