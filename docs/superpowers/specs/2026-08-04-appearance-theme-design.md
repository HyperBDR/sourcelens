# Appearance Theme Design

## Goal

Add a reliable appearance preference that applies consistently to the login
page, user workspace, chat interface, and public user-facing pages without
changing existing layout geometry.

The dark theme must match Cursor's neutral dark-gray appearance. It must not
use blue-tinted slate colors.

Administration pages are explicitly excluded from dark mode. Every
`/management/*` route must retain the current administration appearance even
when the user's saved preference resolves to dark.

## Confirmed Product Scope

- Use only the existing user settings modal as the appearance entry point.
- Offer four mutually exclusive modes:
  - Light
  - Dark
  - Follow system
  - Scheduled
- Scheduled mode uses dark appearance from 20:00 through 06:59 local time.
- Persist the selected mode in local storage.
- Apply the resolved appearance before Vue mounts to prevent a light flash.
- Apply one global preference to:
  - Authentication pages
  - User workspace pages
  - Chat pages
  - Public user-facing pages
  - Shared user-facing modals, drawers, menus, date pickers, tables, and toasts
- Force the light appearance on every `/management/*` route.
- Restore the user's resolved preference immediately after leaving
  `/management/*`.
- Keep teleported administration UI light while an administration route is
  active.

The feature does not add a header shortcut or synchronize preferences to the
backend. It does not migrate administration pages or charts to dark mode.

## Visual Tokens

Light mode preserves the current product appearance. Dark mode uses these
neutral semantic values:

| Semantic role | Dark value |
| --- | --- |
| Page canvas | `#1e1e1e` |
| Surface and input | `#252526` |
| Hover and raised surface | `#2a2d2e` |
| Selected surface | `#333333` |
| Default border | `#3c3c3c` |
| Strong border | `#454545` |
| Primary text | `#cccccc` |
| Secondary text | `#b4b4b4` |
| Muted text | `#858585` |

Brand and status colors retain their identities but must meet WCAG AA contrast
against dark surfaces.

## Theme Architecture

### Preference state

The existing Pinia preferences store owns:

- `themeMode`
- the resolved effective theme
- local storage persistence
- system color-scheme observation
- scheduled-mode boundary refresh

Valid stored values are `light`, `dark`, `system`, and `scheduled`. Invalid or
missing values resolve to `system`.

### Root theme application

The effective theme is represented on `document.documentElement` using a
`data-theme="light|dark"` attribute and the matching `color-scheme` value.

Theme resolution happens before `app.mount()`. System mode listens for
`prefers-color-scheme` changes. Scheduled mode refreshes at the next 07:00 or
20:00 boundary rather than polling continuously.

The preferences store also owns a transient route theme override. The router
sets that override to `light` for `/management/*` routes and clears it for all
other routes. Applying the theme uses the route override when present and the
user's resolved preference otherwise. The override is never persisted and
never changes the selected mode.

The initial route must establish the override before the application becomes
visible so that directly loading or refreshing an administration URL cannot
flash a dark canvas. Because the override is applied on the document root,
administration dialogs and drawers teleported to `body` remain light as well.

### Semantic color layer

Global CSS variables define canvas, surfaces, text, borders, overlays, and
form controls for both themes. Existing Tailwind semantic colors reference
those variables.

Components must consume semantic tokens instead of hard-coded light colors.
The implementation must not introduce a global `!important` override layer.
Existing broad form-control overrides must be converted to token values.

## Logo Invariants

Logo layout is theme-independent:

- Use the same transparent source asset in light and dark modes.
- Use the same DOM elements in both modes.
- Preserve the existing width, height, object-fit, wrapper gap, alignment,
  margin, and positioning.
- Dark mode may alter only the rendered colors of the transparent asset.
- Do not switch to the current dark wordmark asset because its canvas aspect
  ratio differs from the light asset.
- Do not use cropping, scaling compensation, blend-mode backgrounds, black
  wrappers, or theme-specific geometry.

The same rule applies to wordmarks and assistant mark avatars.

Automated tests must compare the logo bounding box before and after theme
switching and require identical coordinates and dimensions.

## Component Migration

### Shared foundation

Migrate the root application, global forms, shared modal, drawer, input,
button, pagination, menu, loading, toast, date picker, and markdown styles
first. This provides consistent behavior for teleported UI.

### User-facing shell

Replace fixed light colors in authentication, application layout, sidebar,
settings modal, assistant switcher, and public headers with semantic tokens.

### Chat

Migrate the chat page's scoped styles in coherent groups:

1. Canvas, sidebar, header, and separators
2. Session list and user dock
3. Messages, markdown, code, file cards, and runtime cards
4. Composer, attachment controls, and bottom gradient
5. Mobile top bar and responsive states

No visible white separator may remain in dark mode.

### Administration exclusion

Keep the existing administration layout, navigation, content colors, charts,
and component classes unchanged. Do not replace administration page colors
with theme tokens solely for dark-mode support.

Shared components may consume semantic tokens for user-facing pages, but their
computed colors must resolve to the light token set while `/management/*` is
active. Any administration or formatting changes already introduced only for
the discarded administration-dark-mode scope must be removed from this change.

## Accessibility

- Normal text contrast must be at least 4.5:1.
- Large text and non-text controls must be at least 3:1.
- Focus indicators must remain visible in both themes.
- Theme choices must be keyboard accessible and expose their selected state.
- Appearance names and descriptions must be available in Chinese and English.
- Theme changes must not move focus or alter page layout.
- Entering or leaving administration routes must not change the saved theme
  choice.

## Testing Strategy

### Unit and source-contract tests

Write failing tests before implementation for:

- Mode validation and persistence
- System mode resolution
- Scheduled mode resolution at both boundaries
- Root attribute and `color-scheme` application
- Administration route override and restoration
- Settings modal wiring and translations
- Logo single-asset and geometry invariants

### Browser tests

Use Playwright with mocked authenticated users where possible:

- Verify all four modes from the settings modal.
- Verify persistence after reload.
- Verify system changes with emulated media.
- Verify scheduled behavior with a fixed browser clock.
- Compare logo bounding boxes in light and dark modes.
- Check computed background, text, and border colors.
- Capture chat and login screenshots in light and dark modes.
- Verify representative administration routes stay light for every saved mode.
- Verify a directly loaded administration route has no dark flash.
- Verify leaving administration restores the previously resolved user theme.
- Open representative user-facing modal, drawer, menu, and date picker states.
- Test desktop and mobile chat layouts.

The browser console must contain no new errors or warnings.

## Delivery Sequence

1. Add failing theme-state tests.
2. Implement preference resolution and pre-mount application.
3. Add semantic variables and migrate shared controls.
4. Add the settings appearance section.
5. Migrate login and user workspace shells.
6. Migrate chat in visual slices.
7. Add the administration light-theme route override.
8. Remove theme-only administration and unrelated formatting changes.
9. Add complete browser coverage and screenshot verification.

Each stage must build and pass its focused tests before the next stage starts.

## Acceptance Criteria

- Switching appearance changes the complete visible page, not only the modal.
- Dark colors match the approved neutral palette.
- No blue-tinted dark canvas or white separator remains.
- Logo position and size are pixel-identical across themes.
- No logo has a black rectangular background.
- Login and post-login pages resolve to the same effective appearance.
- Every `/management/*` route remains in the current light administration
  appearance for all four saved modes.
- Administration dialogs, drawers, menus, and charts remain light.
- Leaving administration restores the user's resolved appearance without
  changing the saved mode.
- Directly loading an administration URL does not flash dark styling.
- Refreshing preserves the selected mode.
- System and scheduled modes update without manual refresh.
- Light mode has no visual regression from the current baseline.
