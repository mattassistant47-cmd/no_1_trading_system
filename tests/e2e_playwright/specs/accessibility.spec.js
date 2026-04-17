import { test, expect } from '@playwright/test'

const routes = [
  { path: '/', h1: 'Dashboard' },
  { path: '/positions', h1: 'Positions' },
  { path: '/trades', h1: 'Trade History' },
  { path: '/strategies', h1: 'Strategies' },
  { path: '/risk', h1: 'Risk Monitoring' },
  { path: '/system', h1: 'System Status' },
]

test.describe('Accessibility', () => {
  for (const { path, h1 } of routes) {
    test(`${path} has a proper h1`, async ({ page }) => {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      const h1Elem = page.locator('h1').first()
      await expect(h1Elem).toBeVisible()
      const text = await h1Elem.textContent()
      expect(text.toLowerCase()).toContain(h1.toLowerCase().split(' ')[0])
    })
  }

  test('buttons have accessible labels/text or title attributes', async ({ page }) => {
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    const buttons = await page.locator('button').all()
    for (const btn of buttons) {
      const text = (await btn.textContent()) || ''
      const title = (await btn.getAttribute('title')) || ''
      const aria = (await btn.getAttribute('aria-label')) || ''
      expect(text.trim().length + title.length + aria.length).toBeGreaterThan(0)
    }
  })

  test('text inputs have placeholder or label', async ({ page }) => {
    await page.goto('/trades')
    await page.waitForLoadState('networkidle')
    const inputs = await page.locator('input[type="text"], input[type="date"]').all()
    for (const input of inputs) {
      const placeholder = (await input.getAttribute('placeholder')) || ''
      const id = await input.getAttribute('id')
      const hasLabel = id ? (await page.locator(`label[for="${id}"]`).count()) > 0 : false
      const hasNearbyLabel = await input.locator('xpath=preceding-sibling::label').count() > 0
      expect(placeholder.length > 0 || hasLabel || hasNearbyLabel || (await input.getAttribute('type')) === 'date').toBeTruthy()
    }
  })

  test('tables have proper <thead> headers', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const tables = await page.locator('table').all()
    for (const table of tables) {
      const thCount = await table.locator('thead th').count()
      expect(thCount).toBeGreaterThan(0)
    }
  })

  test('no images without alt attribute', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const imgs = await page.locator('img').all()
    for (const img of imgs) {
      const alt = await img.getAttribute('alt')
      expect(alt).not.toBeNull()
    }
  })

  test('main content region present on each page', async ({ page }) => {
    for (const { path } of routes) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      const main = page.locator('main')
      await expect(main).toBeVisible()
    }
  })
})
