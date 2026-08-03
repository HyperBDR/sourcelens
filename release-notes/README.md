# Release-note fragments

Every pull request must either add a user-facing release-note fragment here or
carry the `skip-release-note` label.

Use the issue or pull-request number as the filename when possible:

```yaml
type: feature
audience: user
en: Added email and verification-code sign-in.
zh-CN: 新增邮箱和验证码登录方式。
```

Supported types are `feature`, `improvement`, and `fix`. Both translations are
required. Set `audience` to `user` for changes relevant to every user, or
`admin` for administrator-only product changes. Administrators see both
audiences in the application; other users see only `user` entries.

Audience filtering is presentation targeting, not a confidentiality boundary.
All fragments are embedded in the frontend image and included in the public
GitHub Release, so keep each entry concise, user-facing, and free of customer
data, credentials, infrastructure details, or unnecessary security details.

Use `skip-release-note` only when a change has no user-visible product impact,
such as tests, refactoring, CI maintenance, or internal documentation.

Tag builds collect only fragments added after the previous `v*` tag. They
generate the English GitHub Release body and embed the bilingual manifest in
the frontend image.
