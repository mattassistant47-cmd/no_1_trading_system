import { test, expect } from '@playwright/test'

const pages = ['/', '/positions', '/trades', '/strategies', '/risk', '/system']

for (const path of pages) {
  test(`${path} loads without errors`, async ({ page }) => {
    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error' && !msg.text().includes('WebSocket')) {
        errors.push(msg.text())
      }
    })

    await page.goto(path)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    // Should not show error banner
    const errorBanner = page.locator('text=/Error loading/i')
    await expect(errorBanner).toHaveCount(0)

    expect(errors.slice(0, 5)).toEqual([])
  })
}
