import { expect, test } from '@playwright/test'

import { asRole, fixtures } from './helpers.js'

const f = fixtures()

test.describe('Management: standardized table actions', () => {
  test.beforeEach(async ({ page }) => {
    await asRole(page, 'admin')
  })

  test('selects current-page users and opens the row action menu', async ({
    page
  }) => {
    await page.goto('/management/users')
    const username = f.users.user
    const row = page.locator('tbody tr').filter({ hasText: username }).first()

    await row.getByRole('checkbox', { name: `Select ${username}` }).check()
    const bulkActions = page.getByRole('region', { name: 'Bulk actions' })
    await expect(bulkActions).toContainText('1 selected')

    await row.getByRole('button', { name: 'More Actions' }).click()
    const menu = page.getByRole('menu')
    await expect(menu.getByRole('menuitem', { name: 'Edit' })).toBeVisible()
    await expect(
      menu.getByRole('menuitem', { name: /Enable|Disable/ })
    ).toBeVisible()

    await menu.getByRole('menuitem', { name: 'Edit' }).press('Escape')
    await expect(menu).toBeHidden()
    await expect(
      row.getByRole('button', { name: 'More Actions' })
    ).toBeFocused()

    await bulkActions.getByRole('button', { name: 'Disable' }).click()
    const bulkResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/management/users/bulk-status/') &&
        response.request().method() === 'POST'
    )
    await bulkActions.getByRole('button', { name: 'Confirm' }).click()
    await expect(await bulkResponse).toBeOK()
    await expect(row.getByText('Disabled')).toBeVisible()
  })

  test('requires confirmation before a bulk group delete', async ({ page }) => {
    await page.goto('/management/groups')
    await page.getByRole('checkbox', { name: 'Select all' }).check()

    const bulkActions = page.getByRole('region', { name: 'Bulk actions' })
    await bulkActions.getByRole('button', { name: 'Delete' }).click()
    await expect(bulkActions).toContainText(
      'Apply this action to the selected rows?'
    )

    await bulkActions.getByRole('button', { name: 'Cancel' }).click()
    await expect(
      bulkActions.getByRole('button', { name: 'Delete' })
    ).toBeVisible()
  })
})
