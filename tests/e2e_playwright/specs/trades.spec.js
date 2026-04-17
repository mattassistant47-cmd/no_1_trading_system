import { test, expect } from '@playwright/test'

test.describe('Trades', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/trades')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with h1 "Trade History"', async ({ page }) => {
    await expect(page.locator('h1:has-text("Trade History")')).toBeVisible()
  })

  test('Win Rate KPI card present (when stats available)', async ({ page }) => {
    const winRate = page.locator('text=Win Rate')
    const empty = page.locator('text=No trades yet')
    const visible = (await winRate.count()) + (await empty.count())
    expect(visible).toBeGreaterThan(0)
  })

  test('stats cards present when data available', async ({ page }) => {
    const winRate = await page.locator('text=Win Rate').count()
    if (winRate === 0) test.skip()
    await expect(page.locator('text=Avg Win').first()).toBeVisible()
    await expect(page.locator('text=Avg Loss').first()).toBeVisible()
    await expect(page.locator('text=Profit Factor').first()).toBeVisible()
    await expect(page.locator('text=Total Trades').first()).toBeVisible()
  })

  test('P&L Distribution chart section present', async ({ page }) => {
    await expect(page.locator('text=P&L Distribution')).toBeVisible()
  })

  test('Cumulative P&L chart section present', async ({ page }) => {
    await expect(page.locator('text=Cumulative P&L')).toBeVisible()
  })

  test('Start Date filter input present', async ({ page }) => {
    const input = page.locator('input[type="date"]').first()
    await expect(input).toBeVisible()
    await input.fill('2024-01-01')
    await page.waitForTimeout(300)
    await expect(input).toHaveValue('2024-01-01')
  })

  test('End Date filter input present', async ({ page }) => {
    const inputs = page.locator('input[type="date"]')
    await expect(inputs.nth(1)).toBeVisible()
  })

  test('Symbol/strategy filter works', async ({ page }) => {
    const filter = page.locator('input[placeholder*="Symbol or strategy"]')
    await expect(filter).toBeVisible()
    await filter.fill('ZZZZZ_FAKE')
    await page.waitForTimeout(300)
    await expect(page.locator('text=No trades yet')).toBeVisible()
  })

  test('empty state "No trades yet" shown when filtered out', async ({ page }) => {
    const filter = page.locator('input[placeholder*="Symbol or strategy"]')
    await filter.fill('XYZZZ_NO_MATCH')
    await page.waitForTimeout(300)
    await expect(page.locator('text=No trades yet')).toBeVisible()
  })

  test('trades table has proper columns when trades exist', async ({ page }) => {
    const rowCount = await page.locator('tbody tr').count()
    if (rowCount === 0) test.skip()
    const expectedHeaders = ['Date', 'Symbol', 'Side', 'Qty', 'Entry', 'Exit', 'P&L', 'Strategy']
    for (const h of expectedHeaders) {
      await expect(page.locator(`th:has-text("${h}")`).first()).toBeVisible()
    }
  })

  test('no console errors (except WebSocket)', async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket') && !msg.text().includes('ws://')) {
        errors.push(msg.text())
      }
    })
    await page.goto('/trades')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })

  test('fetches /api/trades on load', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/trades')) requests.push(req.url())
    })
    await page.goto('/trades')
    await page.waitForLoadState('networkidle')
    expect(requests.length).toBeGreaterThan(0)
  })
})
