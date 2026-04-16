#!/bin/bash
set -euo pipefail
REPO_URL="${REPO_URL:-https://github.com/mattassistant47-cmd/no_1_trading_system.git}"
BASE_DIR="$HOME/trading-bot"

echo "=== Installing prerequisites ==="
sudo apt-get update && sudo apt-get install -y git curl ufw fail2ban

if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
fi

if ! docker compose version &>/dev/null; then
    sudo apt-get install -y docker-compose-plugin
fi

echo "=== Creating directories ==="
mkdir -p "$BASE_DIR"/{dev,prod,code}
mkdir -p "$BASE_DIR"/dev/{logs,test-reports}
mkdir -p "$BASE_DIR"/prod/logs

echo "=== Cloning repo ==="
if [ ! -d "$BASE_DIR/code/.git" ]; then
    git clone "$REPO_URL" "$BASE_DIR/code"
else
    cd "$BASE_DIR/code" && git pull origin main
fi

echo "=== Copying configs ==="
cp "$BASE_DIR/code/docker-compose.dev.yml" "$BASE_DIR/dev/"
cp "$BASE_DIR/code/docker-compose.prod.yml" "$BASE_DIR/prod/"
cp "$BASE_DIR/code/nginx.dev.conf" "$BASE_DIR/dev/"
cp "$BASE_DIR/code/nginx.prod.conf" "$BASE_DIR/prod/"

echo "=== Generating env files ==="
if [ ! -f "$BASE_DIR/dev/.env" ]; then
    cat > "$BASE_DIR/dev/.env" << EOF
DB_USER=trading_dev
DB_PASSWORD=$(openssl rand -hex 16)
DB_NAME=trading_dev_db
ALPACA_API_KEY_PAPER=PLACEHOLDER
ALPACA_API_SECRET_PAPER=PLACEHOLDER
FRED_API_KEY=PLACEHOLDER
JWT_SECRET_KEY=$(openssl rand -hex 32)
EOF
    echo "Dev .env created — update API keys!"
fi

if [ ! -f "$BASE_DIR/prod/.env" ]; then
    cat > "$BASE_DIR/prod/.env" << EOF
DB_USER=trading_prod
DB_PASSWORD=$(openssl rand -hex 16)
DB_NAME=trading_prod_db
TRADING_MODE=paper
ALPACA_API_KEY_PAPER=PLACEHOLDER
ALPACA_API_SECRET_PAPER=PLACEHOLDER
FRED_API_KEY=PLACEHOLDER
JWT_SECRET_KEY=$(openssl rand -hex 32)
EOF
    echo "Prod .env created — update API keys!"
fi

echo "=== Configuring firewall ==="
sudo ufw --force enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
for port in 22 80 443 8000 8001 8080; do
    sudo ufw allow $port/tcp
done

echo "=== Creating swap ==="
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

sudo systemctl enable fail2ban && sudo systemctl start fail2ban

echo "=== Setup complete ==="
echo "Dev: $BASE_DIR/dev/"
echo "Prod: $BASE_DIR/prod/"
echo "Code: $BASE_DIR/code/"
