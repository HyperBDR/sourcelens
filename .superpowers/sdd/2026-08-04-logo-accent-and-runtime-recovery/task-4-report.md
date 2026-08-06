# Task 4 Report: Runtime Synchronization and Browser Acceptance

## Shared runtime synchronization

    Synchronized 51 changed paths from 3 worktrees into
    /Users/apple/.codex/worktrees/4b70/sourcelens/.worktree-runtime/source

Exit status: 0. No overlay conflict was reported.

## Appearance Playwright suite

Command:

    cd frontend
    BASE_URL=http://localhost:8000 npx playwright test
    e2e/ui-regression/appearance-theme.spec.js
    --config=playwright.ui.config.cjs --reporter=line

Result: 3 passed, 1 failed, 4 total (8.6 s).

The failing test was user-facing logo keeps its source and geometry across
themes at appearance-theme.spec.js:115. It expects
logo_with_text_dark_transparent.png, but the actual dark source was
/brand/logo_dark_transparent.png. No source changes were made during this
verification task.

## Chrome acceptance

- Existing user-facing Chrome tab:
  http://localhost:8000/lens/assistants/dev/chat (dark mode).
- Visual confirmation: the SourceLens wordmark and mark body are white; the
  center dot is blue-purple.
- Assistants page: http://localhost:8000/management/lens/assistants.
  The page content remains light and displays Assistant · 7, with
  Showing 1 - 7 of 7.
- The existing user localhost:8000 chat tab was retained. The temporary
  assistants verification tab was closed.

## Final repository checks

git diff --check exited 0 with no whitespace errors.

git status --short:

    M frontend/src/App.vue
    M frontend/src/assets/css/main.css
    M frontend/src/components/auth/LoginModal.vue
    M frontend/src/components/layout/AppHeader.vue
    M frontend/src/components/layout/AppSidebar.vue
    M frontend/src/components/layout/SidebarQuickMenu.vue
    M frontend/src/components/lens/AssistantEmptyState.vue
    M frontend/src/components/lens/AssistantSwitcher.vue
    M frontend/src/components/lens/PublicLensHeader.vue
    M frontend/src/components/lens/UserDock.vue
    M frontend/src/components/settings/UserSettingsModal.vue
    M frontend/src/components/ui/ActivityNotificationStack.vue
    M frontend/src/components/ui/BaseDrawer.vue
    M frontend/src/components/ui/BaseInput.vue
    M frontend/src/components/ui/BaseLoading.vue
    M frontend/src/components/ui/BaseModal.vue
    M frontend/src/components/ui/BaseSelect.vue
    M frontend/src/components/ui/ErrorBoundary.vue
    M frontend/src/components/ui/LanguageSwitcher.vue
    M frontend/src/components/ui/MarkdownRenderer.vue
    M frontend/src/components/ui/PaginationBar.vue
    M frontend/src/locales/en.json
    M frontend/src/locales/zh-CN.json
    M frontend/src/main.js
    M frontend/src/pages/Auth.vue
    M frontend/src/pages/lens/Chat.vue
    M frontend/src/store/preferences.js
    M frontend/tailwind.config.js
    ?? .superpowers/
    ?? docs/superpowers/plans/
    ?? frontend/src/utils/theme.js

## Fix round 1: Logo assertion and dark composer gradient

### Failure evidence and root cause

The appearance suite previously failed because the login-page regression test
expected the dark wordmark asset. Login renders BrandLogo with variant=mark,
so its correct dark asset is logo_dark_transparent.png.

The supplied dark chat screenshot showed a large white band behind the bottom
composer. The concrete source was Chat.vue .composer-wrap, whose gradient
contained these hard-coded white stops:

    rgba(255, 255, 255, 0.98)
    rgba(255, 255, 255, 0.78)
    rgba(255, 255, 255, 0)

### Test-first coverage and minimal fix

Added the themePreferences.test.js regression test
chat composer gradient uses semantic surface opacity tokens. Before the CSS
fix, it failed because .composer-wrap did not contain the required
rgb(var(--sl-bg-surface-rgb) / 98%) stop and still contained the hard-coded
white rgba values.

Updated the login test to assert logo_dark_transparent.png while retaining the
dark-source-differs-from-light and identical-bounding-box assertions.

Replaced only the three composer gradient stops with:

    rgb(var(--sl-bg-surface-rgb) / 98%)
    rgb(var(--sl-bg-surface-rgb) / 78%)
    rgb(var(--sl-bg-surface-rgb) / 0%)

This preserves the existing gradient geometry and uses the active surface
color in both light and dark themes.

### Verification

- RED: node --test tests/themePreferences.test.js: 35 passed, 1 failed. The
  failure was the new composer-gradient assertion and showed the old white
  rgba source.
- GREEN: node --test tests/themePreferences.test.js: 36 passed, 0 failed.
- Changed-file ESLint:
  npx eslint src/pages/lens/Chat.vue e2e/ui-regression/appearance-theme.spec.js
  tests/themePreferences.test.js: exit 0, no lint output.
- Build: npm run build: exit 0. Existing baseline-browser-mapping,
  Browserslist-data-age, and Vite dynamic-import warnings were emitted, but
  the production build completed successfully.
- Shared runtime synchronization: exit 0; synchronized 51 changed paths from
  3 worktrees.
- Full appearance Playwright suite: 4 passed, 0 failed (8.8 s).
- Chrome recheck at http://localhost:8000/management/lens/assistants:
  Assistant · 7 and Showing 1 - 7 of 7 were present. The temporary
  verification tab was closed and the user's SourceLens chat tab remains open.
