# Trading Bot E2E Tests

Playwright tests run against the live dev environment through WireGuard VPN.

## Setup
```bash
npm install
npx playwright install chromium
```

## Run
```bash
# Against dev
npm test

# Against prod
BASE_URL=http://10.8.0.1 npm test

# With browser UI
npm run test:headed
```
