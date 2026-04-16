# Deployment Guide - Trading System on OCI ARM64

Complete guide to deploying the autonomous multi-asset trading system on OCI ARM64 free tier (4 CPU, 24GB RAM, Ubuntu).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Client Browser                       │
│                    (React Frontend)                       │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTPS/WSS
┌─────────────────▼───────────────────────────────────────┐
│                   Nginx (Reverse Proxy)                  │
│         Rate Limiting | Compression | SSL/TLS           │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP/WS
┌─────────────────▼───────────────────────────────────────┐
│           FastAPI Backend (2 workers)                    │
│     Trading Logic | Risk Management | API Endpoints     │
└─────────────────┬───────────────────────────────────────┘
                  │ PostgreSQL/TCP
┌─────────────────▼───────────────────────────────────────┐
│      TimescaleDB (PostgreSQL + Time-Series)             │
│         Historical Data | Orders | Positions            │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

- OCI Free Tier ARM64 instance (Ampere A1)
- Ubuntu 20.04/22.04 LTS
- SSH access to instance
- GitHub repository for code

## One-Time Setup

### 1. Initial Instance Configuration

Connect via SSH and run the setup script:

```bash
# On your local machine
ssh -i ~/.ssh/oci_key ubuntu@your-oci-instance-ip

# On OCI instance
wget https://raw.githubusercontent.com/yourrepo/setup_oci.sh
chmod +x setup_oci.sh
./setup_oci.sh
```

The script will:
- Install Docker and Docker Compose
- Install git
- Configure firewall (ports 22, 80, 443)
- Create swap space (4GB) for stability
- Install fail2ban for security
- Setup systemd service for auto-start

### 2. Clone Repository

```bash
cd ~
git clone <your-repo-url> trading-bot
cd trading-bot
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
nano .env
```

Key environment variables:
```env
ENV=production
TRADING_MODE=paper                    # Start with paper trading
DB_USER=trading
DB_PASSWORD=<generate-secure-password>
SECRET_KEY=<generate-secure-key>
API_KEY=<your-api-key>
LOG_LEVEL=INFO
```

### 4. Initial Deployment

```bash
docker-compose up -d

# Verify services started
docker-compose ps
docker-compose logs -f app
```

Check health:
```bash
curl http://localhost:8000/health
curl http://localhost/health
```

## Day-to-Day Operations

### Viewing Logs

```bash
# Follow app logs
docker-compose logs -f app

# View nginx logs
docker-compose logs -f nginx

# View database logs
docker-compose logs -f db
```

### Updating Code

```bash
cd ~/trading-bot
git pull origin main
docker-compose build --no-cache app
docker-compose up -d app
docker-compose logs -f app
```

Or use the deployment script:
```bash
./deploy.sh
```

With options:
```bash
./deploy.sh --no-build    # Skip rebuild
./deploy.sh --rollback    # Revert to previous version
```

### Database Management

#### Backup

```bash
./scripts/backup_db.sh
```

Backups are automatically rotated (7 daily, 4 weekly backups).

#### Restore from Backup

```bash
# Find backup file
ls -la backups/

# Restore
zcat backups/trading_db_YYYYMMDD_HHMMSS.sql.gz | docker-compose exec -T db psql -U trading -d trading_db
```

#### Database CLI Access

```bash
docker-compose exec db psql -U trading -d trading_db
```

### Monitoring

#### Container Health

```bash
# Check container status
docker-compose ps

# Check health check status
docker-compose exec app curl http://localhost:8000/health

# View resource usage
docker stats trading-app trading-db
```

#### Port Verification

```bash
# Check listening ports
sudo netstat -tlnp | grep LISTEN

# Typical output should show:
# :80 -> nginx
# :443 -> nginx (when SSL enabled)
# :5432 -> db
# :8000 -> app (internal)
```

### Scaling Considerations

The system is optimized for OCI free tier (4 CPU, 24GB RAM):

- **FastAPI workers**: 2 (conservative for ARM64)
- **Database shared buffers**: 512MB
- **App memory limit**: 4GB
- **DB memory limit**: Remaining system RAM
- **Swap**: 4GB (critical for stability)

To increase workers in production:
```bash
# Edit docker-compose.yml
# Change: CMD ["uvicorn", "main:app", ..., "--workers", "2"]
# To: CMD ["uvicorn", "main:app", ..., "--workers", "4"]
docker-compose build --no-cache app
docker-compose up -d app
```

## GitHub Actions CI/CD

### CI Pipeline

Automatically runs on every push to main:

1. **Lint** (ruff, mypy) - 3 minutes
2. **Test** (pytest with PostgreSQL) - 5 minutes
3. **Build** (Docker image) - cache enabled

### CD Pipeline

Automatically deploys after CI passes:

1. Connects via SSH to OCI instance
2. Pulls latest code
3. Builds Docker image
4. Restarts containers
5. Runs health checks
6. Rolls back on failure

### Setup GitHub Secrets

Add these to your GitHub repository (Settings > Secrets):

```
OCI_HOST=your-instance-ip-or-domain
OCI_USER=ubuntu
OCI_SSH_KEY=<contents-of-private-key>
```

Generate SSH key on your OCI instance:
```bash
ssh-keygen -t rsa -b 4096 -f /tmp/github_deploy_key
cat /tmp/github_deploy_key
# Copy to GitHub Secrets as OCI_SSH_KEY
cat /tmp/github_deploy_key.pub >> ~/.ssh/authorized_keys
```

## SSL/TLS (HTTPS)

### Setup Let's Encrypt

```bash
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ~/trading-bot/certs/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ~/trading-bot/certs/key.pem
sudo chown -R $USER:$USER ~/trading-bot/certs/
```

Uncomment HTTPS section in `nginx.conf`:
```bash
nano nginx.conf
# Uncomment the 443 server block
docker-compose restart nginx
```

### Auto-renewal

```bash
sudo certbot renew --dry-run  # Test renewal
sudo systemctl enable certbot-renew.timer
sudo systemctl start certbot-renew.timer
```

## Security Checklist

- [ ] Changed all default passwords in `.env`
- [ ] Generated new SECRET_KEY
- [ ] Firewall configured (ports 80, 443 only for HTTP)
- [ ] SSH key-based auth only (no password login)
- [ ] fail2ban installed and running
- [ ] Regular database backups enabled
- [ ] SSL/TLS certificates installed
- [ ] CORS origins properly configured
- [ ] API key rotation configured

## Troubleshooting

### "Connection refused" on app startup

```bash
# Check if database is ready
docker-compose exec db pg_isready -U trading

# View db logs
docker-compose logs db

# Restart in correct order
docker-compose down
docker-compose up -d db
sleep 10
docker-compose up -d app
```

### Out of memory errors

```bash
# Check memory usage
free -h
docker stats

# If needed, increase swap
sudo swapoff /swapfile
sudo fallocate -l 8G /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### High disk usage

```bash
# Check disk space
df -h

# Clean old Docker images/volumes
docker image prune -a
docker volume prune

# Check backup retention
ls -lh backups/
```

### Slow query performance

```bash
# Enable query logging
docker-compose exec db psql -U trading -d trading_db
# ALTER SYSTEM SET log_min_duration_statement = 1000;
# SELECT pg_reload_conf();
```

## Performance Tuning

### For ARM64 Architecture

```bash
# Edit docker-compose.yml for app service:
# Add environment variables:
# - PYTHONOPTIMIZE=2
# - NUMEXPR_NUM_THREADS=2
# - OMP_NUM_THREADS=2
```

### Database Optimization

```bash
docker-compose exec db psql -U trading -d trading_db

-- Check table sizes
SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables WHERE schemaname != 'pg_catalog'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Analyze tables for query planner
ANALYZE;

-- Check index usage
SELECT * FROM pg_stat_user_indexes ORDER BY idx_scan DESC;
```

## Maintenance Schedule

### Daily
- Check logs for errors
- Verify health endpoints
- Monitor disk space

### Weekly
- Review backup integrity
- Check database size
- Update system packages: `sudo apt update && sudo apt upgrade`

### Monthly
- Rotate API keys
- Review security logs
- Performance analysis

### Quarterly
- Major dependency updates
- Security audit
- Disaster recovery drill

## Emergency Procedures

### Rollback to Previous Version

```bash
cd ~/trading-bot
./deploy.sh --rollback
```

### Emergency Stop

```bash
docker-compose down
```

### Data Recovery

```bash
# List available backups
ls -la backups/

# Restore latest backup
latest_backup=$(ls -t backups/ | head -1)
zcat "backups/$latest_backup" | docker-compose exec -T db psql -U trading -d trading_db
```

### Complete Reinstall

```bash
docker-compose down -v  # Warning: deletes all data
rm -rf postgres_data/
git checkout HEAD -- docker-compose.yml
docker-compose up -d
```

## Monitoring and Alerting

### Enable Application Monitoring

```bash
# View application metrics
docker-compose exec app curl http://localhost:8000/status

# Setup monitoring (example with Prometheus)
# Add to docker-compose.yml for production setup
```

### Log Aggregation (Optional)

Consider adding ELK stack for production:
```bash
# elasticsearch + logstash + kibana
# See docker-compose.yml for commented examples
```

## Support and Resources

- GitHub Issues: Report bugs and feature requests
- Documentation: See README.md
- API Docs: http://your-instance/docs
- Strategy Docs: See STRATEGY_FRAMEWORK.md
- API Reference: See API_DOCUMENTATION.md

## Version History

- **1.0.0** - Initial deployment stack for OCI ARM64
  - Multi-stage Docker build
  - TimescaleDB integration
  - Nginx reverse proxy with rate limiting
  - GitHub Actions CI/CD
  - Comprehensive monitoring and logging
