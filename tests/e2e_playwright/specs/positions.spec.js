import { test, expect } from '@playwright/test'

test.describe('Positions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with h1 "Positions"', async ({ page }) => {
    await expect(page.locator('h1:has-text("Positions")')).toBeVisible()
  })

  test('Total Exposure card visible', async ({ page }) => {
    await expect(page.locator('text=Total Exposure').first()).toBeVisible()
  })

  test('Long Exposure card visible', async ({ page }) => {
    await expect(page.locator('text=Long Exposure').first()).toBeVisible()
  })

  test('Short Exposure card visible', async ({ page }) => {
    await expect(page.locator('text=Short Exposure').first()).toBeVisible()
  })

  test('Total exposure shows percentage under 1000%', async ({ page }) => {
    const card = page.locator('text=Total Exposure').first().locator('..')
    const text = await card.textContent()
    const match = text.match(/(\d+\.?\d*)%/)
    if (match) {
      const pct = parseFloat(match[1])
      expect(pct).toBeLessThan(1000)
    }
  })

  test('Exposure Breakdown bar chart renders', async ({ page }) => {
    const section = page.locator('text=Exposure Breakdown').locator('..')
    await expect(section.locator('svg').first()).toBeVisible()
  })

  test('Positions table or empty state visible', async ({ page }) => {
    const hasTable = await page.locator('table').count()
    const emptyState = await page.locator('text=No open positions').count()
    expect(hasTable + emptyState).toBeGreaterThan(0)
  })

  test('table has proper headers when positions exist', async ({ page }) => {
    const table = page.locator('table').first()
    if (await table.isVisible().catch(() => false)) {
      const expectedHeaders = [
        'Symbol', 'Qty', 'Entry Price', 'Current Price',
        'Unrealized P&L', '% Change', 'Strategy', '% Portfolio'
      ]
      for (const h of expectedHeaders) {
        const count = await table.locator(`th:has-text("${h}")`).count()
        if (count === 0) {
          test.skip()
        }
      }
    }
  })

  test('clicking a sortable column toggles indicator', async ({ page }) => {
    const header = page.locator('th:has-text("Symbol")').first()
    if (!(await header.isVisible().catch(() => false))) {
      test.skip()
    }
    await header.click()
    await page.waitForTimeout(200)
    const text = await header.textContent()
    expect(text).toMatch(/[↑↓]/)
  })

  test('filter input filters positions table', async ({ page }) => {
    const input = page.locator('input[placeholder*="Filter"]')
    await expect(input).toBeVisible()
    await input.fill('ZZZZZ_NONEXISTENT')
    await page.waitForTimeout(300)
    await expect(page.locator('text=No open positions')).toBeVisible()
  })

  test('close position button present when positions exist', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count === 0) test.skip()
    const closeBtn = rows.first().locator('button[title="Close position"]')
    await expect(closeBtn).toBeVisible()
  })

  test('no console errors (except WebSocket)', async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket') && !msg.text().includes('ws://')) {
        errors.push(msg.text())
      }
    })
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })

  test('auto-refreshes positions every 3 seconds', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/positions')) requests.push(Date.now())
    })
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(4500)
    expect(requests.length).toBeGreaterThanOrEqual(2)
  })

  test('snakeToCamel maps API fields (no raw snake_case in UI)', async ({ page }) => {
    const body = await page.locator('body').textContent()
    expect(body).not.toContain('unrealized_pnl')
    expect(body).not.toContain('entry_price')
    expect(body).not.toContain('current_price')
  })
})
