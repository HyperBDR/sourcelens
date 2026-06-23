# E2E Notes

Run Playwright from `frontend/`.

```bash
BASE_URL=http://localhost:8000 npx playwright test \
  --config=playwright.config.cjs
```

The local suite uses the dev environment account from `.env.dev` by default:

- `TEST_USERNAME`, default `admin`
- `TEST_PASSWORD`, default `admin`

## Access-control suite (role-based permissions)

`e2e/access-control/` verifies assistant/QA visibility across five roles
(anonymous, plain user, directly-authorized user, group-authorized user,
admin). It is self-contained: `globalSetup` seeds backend fixtures via the
`seed_e2e_access` management command, logs each role in, and writes
`fixtures.json`; `globalTeardown` removes everything.

```bash
BASE_URL=http://localhost:8000 npx playwright test \
  --config=playwright.access.config.cjs
```

Requires the dev backend (`DEBUG=True`) and a LensNode reporting tasks/dirs.
Override the seed runner with `E2E_SEED_EXEC` if the backend is not the
`sourcelens-api-dev` container (default:
`docker exec sourcelens-api-dev python manage.py`).
