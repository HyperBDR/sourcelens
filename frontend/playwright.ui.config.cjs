/**
 * UI-regression tier config — the pure-frontend, mock-driven baseline lens
 * (style / flow consistency, translations, console cleanliness, mobile fit).
 * Distinct from the real-backend access-control tier (playwright.access.config).
 *
 * Serves the built app itself so CI needs only Node — no backend, no DB.
 * Override the command with UI_WEB_CMD if you prefer `vite preview`.
 */
const baseURL = process.env.BASE_URL || 'http://localhost:4173'

module.exports = {
  testDir: './e2e/ui-regression',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 1,
  reporter: process.env.CI ? 'list' : 'html',
  timeout: 30000,
  use: {
    baseURL,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry'
  },
  webServer: {
    command:
      process.env.UI_WEB_CMD ||
      'npm run build && npm run preview -- --port 4173',
    url: baseURL,
    timeout: 180000,
    reuseExistingServer: !process.env.CI
  },
  projects: [{ name: 'chromium', use: { channel: 'chromium' } }]
}
