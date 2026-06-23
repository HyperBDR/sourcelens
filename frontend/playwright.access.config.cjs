/**
 * Playwright config for access-control E2E (role-based permission suite).
 * Separate from the main config so it can seed/teardown backend fixtures.
 *
 *   BASE_URL=http://localhost:8000 \
 *   npx playwright test --config=playwright.access.config.cjs
 */
const baseURL =
  process.env.BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  'http://localhost:8000'

module.exports = {
  testDir: './e2e/access-control',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: require.resolve('./e2e/access-control/global-setup.cjs'),
  globalTeardown: require.resolve('./e2e/access-control/global-teardown.cjs'),
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure'
  },
  projects: [{ name: 'chromium' }],
  timeout: 30000
}
