/**
 * Global teardown: remove the seeded access-control fixtures and local file.
 */
const { execSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const SEED_EXEC =
  process.env.E2E_SEED_EXEC || 'docker exec sourcelens-api-dev python manage.py'

module.exports = async () => {
  try {
    execSync(`${SEED_EXEC} seed_e2e_access --teardown`, { encoding: 'utf-8' })
  } catch (error) {
    console.warn('[e2e access] teardown failed:', error.message)
  }
  try {
    fs.unlinkSync(path.join(__dirname, 'fixtures.json'))
  } catch {
    /* already gone */
  }
}
