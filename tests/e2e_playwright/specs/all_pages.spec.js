import { test, expect } from '@playwright/test'

const pages = [
  { path: '/', title: /N1 Trading/, h1: 'Dashboard' },
  { path: '/positions', title: /N1 Trading/, h1: 'Positions' },
  { path: '/trades', title: /N1 Trading/, h1: 'Trade History' },
  { path: '/strategies', title: /N1 Trading/, h1: 'Strategies' },
  { path: '/risk', title: /N1 Trading/, h1: 'Risk Monitoring' },
  { path: '/system', title: /N1 Trading/, h1: 'System Status' },
]

test.describe('All Pages Smoke', () => {
  for (const { path, title, h1 } of pages) {
    test(`${path} loads without console errors`, async ({ page }) => {
      const errors = []
      page.on('console', msg => {
        if (msg.type() === 'error' && !msg.text().includes('WebSocket') && !msg.text().includes('ws://')) {
          errors.push(msg.text())
        }
      })

      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(1500)

      // No error banner present
      await expect(page.locator('text=/Error loading/i')).toHaveCount(0)

      expect(errors.slice(0, 5)).toEqual([])
    })

    test(`${path} has correct title and h1`, async ({ page }) => {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await expect(page).toHaveTitle(title)
      await expect(page.locator(`h1:has-text("${h1}")`)).toBeVisible()
    })

    test(`${path} issues at least one API request`, async ({ page }) => {
      const apiRequests = []
      page.on('request', req => {
        if (req.url().includes('/api/')) apiRequests.push(req.url())
      })
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(800)
      expect(apiRequests.length).toBeGreaterThan(0)
    })
  }
})
