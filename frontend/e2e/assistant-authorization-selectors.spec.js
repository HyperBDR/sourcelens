import { expect, test } from '@playwright/test'

const assistant = {
  uuid: 'private-assistant',
  name: 'Private Assistant',
  slug: 'private-assistant',
  status: 'active',
  visibility: 'private',
  lensnode: 'test-lensnode',
  selected_task: 'general_chat',
  agent_model_ref: 'test-model',
  skill_bindings: [{ skill_uuid: 'test-skill', enabled: true }],
  access_grants: [
    { type: 'group', id: 201, name: 'Assigned Outside Group Page' },
    {
      type: 'user',
      id: 101,
      name: 'assigned-outside-user',
      username: 'assigned-outside-user',
      email: 'assigned@example.com'
    }
  ]
}

async function mockAssistantsPage(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'test-token')
    localStorage.setItem('userLanguage', 'en')
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let payload = []

    if (path === '/api/v1/auth/user') {
      payload = { username: 'admin', is_staff: true }
    } else if (path === '/api/lens/assistants/') {
      payload = [assistant]
    } else if (path === '/api/lens/admin/lensnodes/') {
      payload = [
        {
          uuid: 'test-lensnode',
          name: 'Test LensNode',
          tasks: [{ name: 'general_chat', title: 'General Chat' }]
        }
      ]
    } else if (path === '/api/lens/admin/skills/') {
      payload = [{ uuid: 'test-skill', name: 'Test Skill', slug: 'test-skill' }]
    } else if (path === '/api/v1/admin/llm-config/all/') {
      payload = [
        {
          uuid: 'test-model',
          provider: 'test',
          config: { model: 'test-model' }
        }
      ]
    } else if (path === '/api/v1/management/groups/') {
      const requestedPage = Number(url.searchParams.get('page'))
      payload = {
        count: 21,
        page: requestedPage,
        page_size: 20,
        results:
          requestedPage === 2
            ? [{ id: 301, name: 'Group From Page Two' }]
            : [{ id: 1, name: 'Default Group' }]
      }
    } else if (path === '/api/v1/management/users/') {
      const search = url.searchParams.get('search')
      payload = {
        count: 1,
        page: 1,
        page_size: 20,
        results: search
          ? [
              {
                id: 8,
                username: 'search-target',
                display_name: 'search-target',
                email: 'target@example.com'
              }
            ]
          : [
              {
                id: 1,
                username: 'default-user',
                display_name: 'default-user',
                email: 'default@example.com'
              }
            ]
      }
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: payload })
    })
  })
}

async function openAccessStep(page) {
  await page.goto('/management/lens/assistants')
  await page.getByRole('button', { name: 'Edit' }).click()
  const drawer = page.locator('.fixed.inset-0.z-50')
  await drawer.getByRole('button', { name: 'Next' }).click()
  await drawer.getByRole('button', { name: 'Next' }).click()
  await drawer.getByRole('button', { name: 'Next' }).click()
  return drawer
}

test('keeps assignments visible while users search and groups paginate', async ({
  page
}) => {
  await mockAssistantsPage(page)
  const userRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === '/api/v1/management/users/' &&
      url.searchParams.get('assignable') === 'true'
    )
  })
  const drawer = await openAccessStep(page)
  await userRequest

  const groupSelector = drawer.getByTestId('authorized-groups-selector')
  const userSelector = drawer.getByTestId('authorized-users-selector')
  await expect(groupSelector.getByTestId('authorized-group-option')).toHaveText(
    [/Assigned Outside Group Page/, /Default Group/]
  )
  await expect(userSelector.getByTestId('authorized-user-option')).toHaveText([
    /assigned-outside-user.*assigned@example.com/s,
    /default-user.*default@example.com/s
  ])

  await groupSelector.getByRole('button', { name: 'Next' }).click()
  await expect(groupSelector.getByTestId('authorized-group-option')).toHaveText(
    [/Assigned Outside Group Page/, /Group From Page Two/]
  )

  await userSelector
    .getByTestId('authorized-user-option')
    .first()
    .getByRole('checkbox')
    .uncheck()
  await expect(drawer.getByTestId('authorized-users-count')).toHaveText('0')

  const searchRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.searchParams.get('search') === 'target'
  })
  await drawer.getByTestId('authorized-user-search').fill('target')
  await searchRequest
  const searchResult = userSelector
    .getByTestId('authorized-user-option')
    .filter({ hasText: 'search-target' })
  await searchResult.getByRole('checkbox').check()
  await expect(drawer.getByTestId('authorized-users-count')).toHaveText('1')

  const defaultRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === '/api/v1/management/users/' &&
      !url.searchParams.has('search')
    )
  })
  await drawer.getByTestId('authorized-user-search').fill('')
  await defaultRequest
  await expect(userSelector.getByTestId('authorized-user-option')).toHaveText([
    /search-target.*target@example.com/s,
    /default-user.*default@example.com/s
  ])
  await expect(drawer.getByTestId('authorized-users-count')).toHaveText('1')
})
