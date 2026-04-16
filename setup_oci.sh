#!/bin/bash
# One-time OCI ARM64 Instance Setup Script
# Run once on fresh Ubuntu instance to prepare for trading system deployment
# Usage: chmod +x setup_oci.sh && ./setup_oci.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_PATH="${APP_PATH:=$HOME/trading-bot}"
SWAP_SIZE="${SWAP_SIZE:=4G}"
DB_USER="${DB_USER:=trading}"
DB_PASSWORD="${DB_PASSWORD:=}"

echo -e "${BLUE}=== OCI ARM64 Trading System Setup ===${NC}"

# Check if running as root (not required, but useful for some operations)
if [[ $EUID -ne 0 ]]; then
   echo -e "${BLUE}Note: Running as non-root. Some operations may require sudo.${NC}"
fi

# Step 1: Update system
echo -e "${BLUE}[1/10] Updating system packages...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

# Step 2: Install Docker
echo -e "${BLUE}[2/10] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh

    # Add current user to docker group
    sudo usermod -aG docker $USER
    echo -e "${GREEN}Docker installed. You may need to log out and back in.${NC}"
else
    echo -e "${GREEN}Docker already installed${NC}"
fi

# Step 3: Install Docker Compose
echo -e "${BLUE}[3/10] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}Docker Compose installed${NC}"
else
    echo -e "${GREEN}Docker Compose already installed${NC}"
fi

# Step 4: Install git
echo -e "${BLUE}[4/10] Installing git...${NC}"
sudo apt-get install -y git

# Step 5: Create application directory
echo -e "${BLUE}[5/10] Creating application directory...${NC}"
mkdir -p "$APP_PATH"
cd "$APP_PATH"

# Step 6: Configure firewall
echo -e "${BLUE}[6/10] Configuring firewall...${NC}"
sudo apt-get install -y ufw
sudo ufw --force enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 8000/tcp   # API (if exposing directly)
echo -e "${GREEN}Firewall configured${NC}"

# Step 7: Clone repository (if REPO_URL is provided)
echo -e "${BLUE}[7/10] Setting up git repository...${NC}"
if [ -z "$(git rev-parse --git-dir 2> /dev/null)" ]; then
    if [ -n "${REPO_URL:-}" ]; then
        git clone "$REPO_URL" .
        echo -e "${GREEN}Repository cloned${NC}"
    else
        echo -e "${BLUE}No REPO_URL provided. Initialize git manually later.${NC}"
    fi
else
    echo -e "${GREEN}Already in a git repository${NC}"
fi

# Step 8: Setup environment file
echo -e "${BLUE}[8/10] Setting up environment configuration...${NC}"
if [ ! -f .env ]; then
    cat > .env << EOF
# Trading System Environment Configuration
ENV=production
TRADING_MODE=paper

# Database
DB_USER=$DB_USER
DB_PASSWORD=${DB_PASSWORD:-$(openssl rand -base64 32)}
DB_NAME=trading_db

# API Security
SECRET_KEY=$(openssl rand -base64 32)
API_KEY=$(openssl rand -base64 32)

# Logging
LOG_LEVEL=INFO

# Optional: External services
# BROKER_API_KEY=
# BROKER_SECRET=
EOF
    echo -e "${GREEN}.env file created. Update with your credentials!${NC}"
else
    echo -e "${BLUE}.env already exists${NC}"
fi

# Step 9: Create swap space (important for ARM with 4GB RAM)
echo -e "${BLUE}[9/10] Creating swap space (${SWAP_SIZE})...${NC}"
if [ ! -f /swapfile ]; then
    # Check available disk space
    AVAILABLE=$(df / | tail -1 | awk '{print $4}')
    SWAP_BYTES=$(numfmt --from=iec $SWAP_SIZE 2>/dev/null || echo 4294967296)

    if [ "$AVAILABLE" -gt "$((SWAP_BYTES / 1024))" ]; then
        sudo fallocate -l $SWAP_SIZE /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile

        # Make permanent
        if ! grep -q '/swapfile' /etc/fstab; then
            echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
        fi
        echo -e "${GREEN}Swap space created${NC}"
    else
        echo -e "${RED}Insufficient disk space for swap${NC}"
    fi
else
    echo -e "${GREEN}Swap space already exists${NC}"
fi

# Step 10: Install fail2ban for security
echo -e "${BLUE}[10/10] Installing fail2ban...${NC}"
sudo apt-get install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
echo -e "${GREEN}fail2ban configured${NC}"

# Setup systemd service for auto-start
echo -e "${BLUE}Creating systemd service for auto-start...${NC}"
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << EOF
[Unit]
Description=Trading Bot Docker Compose Service
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_PATH
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
Restart=on-failure
RestartSec=10s
User=$USER
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trading-bot.service
echo -e "${GREEN}Systemd service created and enabled${NC}"

# Summary
echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Update .env file with your credentials"
echo "2. Ensure repository is cloned/updated"
echo "3. Run: cd $APP_PATH && docker-compose up -d"
echo ""
echo "To view logs: docker-compose logs -f app"
echo "To check status: docker-compose ps"
echo ""
echo "Security notes:"
echo "- Firewall is enabled (SSH, HTTP, HTTPS allowed)"
echo "- fail2ban is protecting SSH"
echo "- Swap space created for stability"
echo "- Docker containers run with memory limits"
echo ""
