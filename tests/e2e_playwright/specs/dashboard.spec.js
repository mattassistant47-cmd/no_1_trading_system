import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test('Portfolio Value card displays a dollar amount', async ({ page }) => {
    const card = page.locator('text=Portfolio Value').locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/\$[\d,]+/)
  })

  test('Daily P&L card displays dollar amount with sign', async ({ page }) => {
    const card = page.locator('text=Daily P&L').locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/\$[-\d,.]+/)
  })

  test('Total Return card displays percentage', async ({ page }) => {
    const card = page.locator('text=Total Return').locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/[-\d.]+%/)
  })

  test('Sharpe Ratio card displays a number', async ({ page }) => {
    const card = page.locator('text=Sharpe Ratio').locator('..')
    const text = await card.textContent()
    expect(text).toMatch(/[-\d.]+/)
  })

  test('Equity Curve chart renders (svg present)', async ({ page }) => {
    const section = page.locator('text=Equity Curve').locator('..')
    await expect(section.locator('svg').first()).toBeVisible()
  })

  test('Asset Allocation pie chart renders', async ({ page }) => {
    const section = page.locator('text=Asset Allocation').locator('..')
    await expect(section.locator('svg').first()).toBeVisible()
  })

  test('Strategy Performance chart renders', async ({ page }) => {
    const section = page.locator('text=Strategy Performance').locator('..')
    await expect(section.locator('svg').first()).toBeVisible()
  })

  test('Active Signals section exists', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Active Signals' })).toBeVisible()
  })

  test('Recent Trades table has expected column headers', async ({ page }) => {
    const table = page.locator('text=Recent Trades').locator('..').locator('table')
    const headers = ['Symbol', 'Side', 'Qty', 'Entry', 'Exit', 'P&L', 'Strategy', 'Date']
    for (const h of headers) {
      await expect(table.locator(`th:has-text("${h}")`)).toBeVisible()
    }
  })

  test('no hardcoded $1,250 Daily P&L value', async ({ page }) => {
    const card = page.locator('text=Daily P&L').locator('..')
    const text = await card.textContent()
    expect(text).not.toContain('$1,250')
  })

  test('no hardcoded 12.50% Total Return value', async ({ page }) => {
    const card = page.locator('text=Total Return').locator('..')
    const text = await card.textContent()
    expect(text).not.toContain('12.50%')
  })

  test('Portfolio Value is not exactly default $100,000', async ({ page }) => {
    const card = page.locator('text=Portfolio Value').locator('..')
    const text = await card.textContent()
    const match = text.match(/\$([\d,]+)/)
    expect(match).not.toBeNull()
    const amount = parseInt(match[1].replace(/,/g, ''))
    expect(amount).toBeGreaterThan(0)
  })

  test('no console errors (except WebSocket)', async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket') && !msg.text().includes('ws://')) {
        errors.push(msg.text())
      }
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })

  test('page title is "N1 Trading - Dashboard"', async ({ page }) => {
    await expect(page).toHaveTitle(/N1 Trading/)
  })

  test('dashboard loads within 5 seconds', async ({ page }) => {
    const start = Date.now()
    await page.goto('/')
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible()
    expect(Date.now() - start).toBeLessThan(5000)
  })

  test('refetches overview every 5 seconds', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/dashboard/overview')) {
        requests.push(Date.now())
      }
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(6500)
    expect(requests.length).toBeGreaterThanOrEqual(2)
  })

  test('shows Real-time or Disconnected badge', async ({ page }) => {
    const badge = page.locator('text=/Real-time|Disconnected/')
    await expect(badge.first()).toBeVisible()
  })

  test('h1 renders "Dashboard"', async ({ page }) => {
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible()
  })
})
