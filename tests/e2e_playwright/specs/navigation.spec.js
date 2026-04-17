import { test, expect } from '@playwright/test'

const navItems = [
  { path: '/', label: 'Dashboard', h1: 'Dashboard' },
  { path: '/positions', label: 'Positions', h1: 'Positions' },
  { path: '/trades', label: 'Trades', h1: 'Trade History' },
  { path: '/strategies', label: 'Strategies', h1: 'Strategies' },
  { path: '/risk', label: 'Risk', h1: 'Risk Monitoring' },
  { path: '/system', label: 'System', h1: 'System Status' },
]

test.describe('Sidebar Navigation', () => {
  test('sidebar shows all 6 nav items', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const aside = page.locator('aside')
    for (const { label } of navItems) {
      await expect(aside.locator(`a:has-text("${label}")`)).toBeVisible()
    }
  })

  test('each nav item renders an icon', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const aside = page.locator('aside')
    for (const { label } of navItems) {
      const link = aside.locator(`a:has-text("${label}")`)
      await expect(link.locator('svg').first()).toBeVisible()
    }
  })

  test('clicking each nav item navigates correctly', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    for (const { path, label, h1 } of navItems) {
      await page.locator('aside').locator(`a:has-text("${label}")`).click()
      await page.waitForLoadState('networkidle')
      await expect(page).toHaveURL(new RegExp(path === '/' ? '/$' : path))
      await expect(page.locator(`h1:has-text("${h1}")`)).toBeVisible()
    }
  })

  test('active nav item has distinguishing style', async ({ page }) => {
    await page.goto('/positions')
    await page.waitForLoadState('networkidle')
    const activeLink = page.locator('aside a:has-text("Positions")')
    const className = await activeLink.getAttribute('class')
    // Active links get border-l-2 + border-neon-green classes
    expect(className).toMatch(/border-neon-green|text-neon-green/)
  })

  test('N1 TRADING logo visible in sidebar', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('aside').getByText('N1 TRADING')).toBeVisible()
  })

  test('sidebar footer shows System and Mode status', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const aside = page.locator('aside')
    await expect(aside.locator('text=System:')).toBeVisible()
    await expect(aside.locator('text=Mode:')).toBeVisible()
  })

  test('main content area changes on navigation', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const dashboardH1 = await page.locator('main h1').textContent()

    await page.locator('aside a:has-text("Positions")').click()
    await page.waitForLoadState('networkidle')
    const positionsH1 = await page.locator('main h1').textContent()

    expect(dashboardH1).not.toBe(positionsH1)
  })

  test('URL updates when navigating', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('aside a:has-text("Risk")').click()
    await page.waitForLoadState('networkidle')
    expect(page.url()).toContain('/risk')
  })

  test('Autonomous Multi-Asset System tagline present', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('text=Autonomous Multi-Asset System')).toBeVisible()
  })
})
