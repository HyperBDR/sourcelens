/**
 * Scenario prototype — a scenario is an ordered list of ATOMIC STEPS, each
 * carrying its own expectation. Written as plain JS objects (same style as
 * routes.js): NO new YAML/JSON format, NO DSL. The `act` is a small function
 * (an action IS code); `expect` is one sentence (the evidence the visual
 * oracle judges against); `assert` is an optional deterministic check.
 *
 * Why per-step `expect` matters: the earlier "login error" case failed only
 * because its intent was vague ("[state=error]") with no definition of what an
 * error state should look like — the visual model had nothing to judge
 * against. Worse, that case never even reached the code path that shows an
 * error (send-code is gated behind a turnstile). Explicit per-step
 * expectations make the MIDDLE of the flow checkable, so the model judges with
 * a basis and real gaps surface where they actually are.
 *
 * A step:
 *   name    short label (report + screenshot filename)
 *   act     async (page, ctx) => {}   perform the action; ctx.installMocks etc.
 *   expect  { en, 'zh-CN' }           what SHOULD now be on screen (visual basis)
 *   assert  async (page, expect)=>{}  optional deterministic check (throws->fail)
 */

const errorMocks = {
  '/api/v1/auth/user': () => ({ status: 401, json: { detail: 'anon' } }),
  // The action under test: sending a code fails server-side.
  '/api/v1/auth/login/send-code': () => ({
    status: 500,
    json: { message: '' }
  })
}

export const scenarios = [
  {
    id: 'login-server-error',
    title: {
      en: 'Login form surfaces a server error when sending a code',
      'zh-CN': '登录页在发送验证码遇到服务器错误时的表现'
    },
    // Route this scenario runs on, and the mocks active from the start.
    path: '/login',
    mocks: errorMocks,
    steps: [
      {
        name: 'open-login',
        act: async (page) => {
          await page.goto('/login')
        },
        expect: {
          en: 'The login form is shown: an email field and a "Send code" button.',
          'zh-CN': '显示登录表单：一个邮箱输入框和一个"发送验证码"按钮。'
        },
        assert: async (page, expect) => {
          await expect(page.getByText('SourceLens').first()).toBeVisible()
        }
      },
      {
        name: 'send-with-500',
        act: async (page) => {
          // Fill the email; bypass the turnstile gate the way a verified user
          // would (the widget sets turnstilePassed=true on @verified), then
          // send. Without passing the turnstile the send path is unreachable —
          // itself a middle-of-flow dependency a final-screen check misses.
          await page.locator('input[type="email"]').first().fill('user@example.com')
          await page.evaluate(() => {
            const btn = [...document.querySelectorAll('button')].find((b) =>
              /send|发送/i.test(b.textContent || '')
            )
            btn && btn.removeAttribute('disabled')
          })
          await page
            .getByRole('button', { name: /send code|发送验证码/i })
            .first()
            .click({ force: true })
        },
        expect: {
          en: 'After the send-code request returns HTTP 500, a visible error message should appear (red text / error banner), e.g. "Failed to send, please try again".',
          'zh-CN':
            '发送验证码请求返回 500 后，应出现可见的错误提示（红色文字/错误横幅），例如"发送失败，请重试"。'
        }
        // No deterministic assert: whether the error banner actually renders is
        // exactly what we let the visual oracle judge against the `expect`.
      }
    ]
  }
]
