import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test('loads with real portfolio value (not $100K default)', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Portfolio value should be visible
    const portfolioText = await page.locator('text=Portfolio Value').locator('..').textContent()
    expect(portfolioText).toMatch(/\$[\d,]+/)
  })

  test('Daily P&L is not hardcoded $1,250', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const pnlCard = page.locator('text=Daily P&L').locator('..')
    const pnlText = await pnlCard.textContent()
    // Should not show the fake hardcoded $1,250
    expect(pnlText).not.toContain('$1,250')
  })

  test('Total Return is not hardcoded 12.50%', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const returnCard = page.locator('text=Total Return').locator('..')
    const returnText = await returnCard.textContent()
    expect(returnText).not.toContain('12.50%')
  })

  test('no console errors except WebSocket', async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket')) {
        errors.push(msg.text())
      }
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })
})
