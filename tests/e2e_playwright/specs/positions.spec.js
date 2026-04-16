import { test, expect } from '@playwright/test'

test.describe('Positions', () => {
  test('page loads', async ({ page }) => {
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('h1:has-text("Positions")')).toBeVisible()
  })

  test('exposure shows percentage not raw dollars', async ({ page }) => {
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    const exposureText = await page.locator('text=Total Exposure').locator('..').textContent()
    // Should not be absurd number like 103241% — should be < 1000%
    const match = exposureText.match(/(\d+\.?\d*)%/)
    if (match) {
      const pct = parseFloat(match[1])
      expect(pct).toBeLessThan(1000)
    }
  })
})
