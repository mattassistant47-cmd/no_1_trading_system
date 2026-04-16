#!/bin/bash
# Manual deployment script for trading bot
# Run on OCI instance: ./deploy.sh [--no-build] [--rollback]
# This script handles pulling latest code, building, and deploying

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
HEALTH_CHECK_URL="http://localhost:8000/health"
HEALTH_CHECK_TIMEOUT=60
HEALTH_CHECK_INTERVAL=2
MAX_RETRIES=30

# Flags
NO_BUILD=false
ROLLBACK=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-build)
            NO_BUILD=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Save current state for rollback
save_state() {
    log_info "Saving deployment state..."
    git rev-parse HEAD > /tmp/deploy_prev_commit.txt || true
    docker compose ps > /tmp/deploy_prev_state.txt || true
}

# Rollback to previous state
perform_rollback() {
    log_error "Deployment failed, rolling back..."

    if [ -f /tmp/deploy_prev_commit.txt ]; then
        PREV_COMMIT=$(cat /tmp/deploy_prev_commit.txt)
        git reset --hard "$PREV_COMMIT"
        log_info "Reverted to commit: $PREV_COMMIT"
    fi

    docker compose down --remove-orphans
    docker compose up -d
    sleep 10

    if health_check; then
        log_success "Rollback successful"
        return 0
    else
        log_error "Rollback failed - manual intervention required"
        return 1
    fi
}

# Health check function
health_check() {
    local retry_count=0

    log_info "Running health checks..."

    while [ $retry_count -lt $MAX_RETRIES ]; do
        if curl -f -s "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
            log_success "Health check passed"
            return 0
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $MAX_RETRIES ]; then
            log_info "Health check attempt $retry_count/$MAX_RETRIES - retrying in ${HEALTH_CHECK_INTERVAL}s..."
            sleep $HEALTH_CHECK_INTERVAL
        fi
    done

    log_error "Health check failed after $MAX_RETRIES attempts"
    return 1
}

# Main deployment function
deploy() {
    log_info "Starting deployment..."

    # Check if we're in the app directory
    if [ ! -f docker-compose.yml ]; then
        log_error "docker-compose.yml not found. Are you in the app directory?"
        exit 1
    fi

    # Save state for rollback
    save_state

    # Step 1: Update code from git
    log_info "Pulling latest code from git..."
    if ! git fetch origin main; then
        log_error "Failed to fetch from git"
        return 1
    fi

    if ! git reset --hard origin/main; then
        log_error "Failed to reset to origin/main"
        return 1
    fi
    log_success "Code updated"

    # Step 2: Build Docker image (unless --no-build)
    if [ "$NO_BUILD" = false ]; then
        log_info "Building Docker image..."
        if ! docker compose build --no-cache app; then
            log_error "Docker build failed"
            return 1
        fi
        log_success "Docker image built"
    else
        log_info "Skipping build (--no-build flag)"
    fi

    # Step 3: Stop old containers
    log_info "Stopping old containers..."
    docker compose down --remove-orphans || true
    log_success "Old containers stopped"

    # Step 4: Start new containers
    log_info "Starting new containers..."
    if ! docker compose up -d; then
        log_error "Failed to start containers"
        return 1
    fi
    log_success "Containers started"

    # Step 5: Wait and perform health check
    log_info "Waiting for services to be ready..."
    sleep 5

    if ! health_check; then
        log_error "Health check failed"
        perform_rollback
        return 1
    fi

    log_success "Deployment completed successfully"
    return 0
}

# Show current status
show_status() {
    echo ""
    log_info "Container status:"
    docker compose ps

    echo ""
    log_info "Recent logs (app container):"
    docker compose logs --tail=20 app || true

    echo ""
    log_info "Recent logs (database):"
    docker compose logs --tail=10 db || true
}

# Main execution
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Trading Bot Deployment Script      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

if [ "$ROLLBACK" = true ]; then
    log_warning "Rolling back to previous deployment..."
    perform_rollback
    show_status
    exit $?
fi

# Execute deployment
if deploy; then
    show_status
    echo ""
    log_success "Deployment script completed successfully"
    exit 0
else
    log_error "Deployment failed"
    show_status
    exit 1
fi
