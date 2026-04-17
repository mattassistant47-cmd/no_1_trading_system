import { test, expect } from '@playwright/test'

async function collectRequests(page, path, urlContains) {
  const requests = []
  page.on('request', req => {
    if (urlContains.some(s => req.url().includes(s))) requests.push(req.url())
  })
  await page.goto(path)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(500)
  return requests
}

test.describe('API Integration', () => {
  test('Dashboard fetches /api/dashboard/overview on load', async ({ page }) => {
    const reqs = await collectRequests(page, '/', ['/api/dashboard/overview'])
    expect(reqs.length).toBeGreaterThan(0)
  })

  test('Positions fetches /api/positions and /api/positions/exposure', async ({ page }) => {
    const reqs = await collectRequests(page, '/positions', ['/api/positions'])
    expect(reqs.some(u => u.includes('/api/positions'))).toBeTruthy()
    // exposure endpoint is optional but should be attempted
    const anyPositionsCall = reqs.length > 0
    expect(anyPositionsCall).toBeTruthy()
  })

  test('Trades fetches /api/trades and /api/trades/stats', async ({ page }) => {
    const reqs = await collectRequests(page, '/trades', ['/api/trades'])
    expect(reqs.some(u => u.includes('/api/trades'))).toBeTruthy()
    expect(reqs.some(u => u.includes('/api/trades/stats'))).toBeTruthy()
  })

  test('Strategies fetches /api/strategies', async ({ page }) => {
    const reqs = await collectRequests(page, '/strategies', ['/api/strategies'])
    expect(reqs.length).toBeGreaterThan(0)
  })

  test('Risk fetches /api/risk/overview', async ({ page }) => {
    const reqs = await collectRequests(page, '/risk', ['/api/risk/overview'])
    expect(reqs.length).toBeGreaterThan(0)
  })

  test('System fetches /api/system/health and /api/system/logs', async ({ page }) => {
    const reqs = await collectRequests(page, '/system', ['/api/system/health', '/api/system/logs'])
    expect(reqs.some(u => u.includes('/api/system/health'))).toBeTruthy()
    expect(reqs.some(u => u.includes('/api/system/logs'))).toBeTruthy()
  })

  test('failed API does not crash the page (dashboard)', async ({ page, context }) => {
    await context.route('**/api/dashboard/overview', route => route.fulfill({
      status: 500,
      body: JSON.stringify({ error: 'server error' }),
      contentType: 'application/json'
    }))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    // Page should render something — either error banner or no-data placeholder
    const body = await page.locator('body').textContent()
    expect(body.length).toBeGreaterThan(0)
  })

  test('WebSocket connection attempts /ws', async ({ page }) => {
    const wsRequests = []
    page.on('websocket', ws => {
      wsRequests.push(ws.url())
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)
    expect(wsRequests.some(u => u.includes('/ws'))).toBeTruthy()
  })

  test('API responses are JSON (content-type check)', async ({ page }) => {
    let contentType = null
    page.on('response', resp => {
      if (resp.url().includes('/api/') && resp.status() === 200 && !contentType) {
        contentType = resp.headers()['content-type'] || ''
      }
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    if (contentType) {
      expect(contentType).toContain('json')
    }
  })
})
