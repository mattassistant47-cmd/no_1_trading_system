import { test, expect } from '@playwright/test'

test.describe('Risk Monitoring', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/risk')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with h1 "Risk Monitoring"', async ({ page }) => {
    await expect(page.locator('h1:has-text("Risk Monitoring")')).toBeVisible()
  })

  test('Circuit Breaker card shows ARMED/TRIPPED/ACTIVE', async ({ page }) => {
    await expect(page.locator('text=CIRCUIT BREAKER')).toBeVisible()
    const status = page.locator('text=/^(ARMED|TRIPPED|ACTIVE)$/')
    await expect(status.first()).toBeVisible()
  })

  test('Current Drawdown card shows percentage', async ({ page }) => {
    await expect(page.locator('text=Current Drawdown')).toBeVisible()
    const card = page.locator('text=Current Drawdown').locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/\d+\.?\d*%/)
  })

  test('Daily Loss card shows dollar amount', async ({ page }) => {
    await expect(page.locator('text=Daily Loss').first()).toBeVisible()
    const card = page.locator('text=Daily Loss').first().locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/\$[-\d,.]+/)
  })

  test('Total Exposure card shows percentage', async ({ page }) => {
    await expect(page.locator('text=Total Exposure').first()).toBeVisible()
    const card = page.locator('text=Total Exposure').first().locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/\d+\.?\d*%/)
  })

  test('Risk Limits Status section present', async ({ page }) => {
    await expect(page.locator('text=Risk Limits Status')).toBeVisible()
  })

  test('Daily Loss Limit progress bar section present', async ({ page }) => {
    await expect(page.locator('text=Daily Loss Limit')).toBeVisible()
  })

  test('Max Drawdown Limit progress bar section present', async ({ page }) => {
    await expect(page.locator('text=Max Drawdown Limit')).toBeVisible()
  })

  test('Position Exposure progress bar section present', async ({ page }) => {
    await expect(page.locator('text=Position Exposure')).toBeVisible()
  })

  test('no console errors (except WebSocket)', async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket') && !msg.text().includes('ws://')) {
        errors.push(msg.text())
      }
    })
    await page.goto('/risk')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })

  test('fetches /api/risk/overview on load', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/risk/overview')) requests.push(req.url())
    })
    await page.goto('/risk')
    await page.waitForLoadState('networkidle')
    expect(requests.length).toBeGreaterThan(0)
  })

  test('auto-refreshes risk data every 3 seconds', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/risk/overview')) requests.push(Date.now())
    })
    await page.goto('/risk')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(4500)
    expect(requests.length).toBeGreaterThanOrEqual(2)
  })
})
