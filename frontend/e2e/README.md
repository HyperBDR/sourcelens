# E2E Notes

Run Playwright from `frontend/`.

```bash
BASE_URL=http://localhost:8000 npx playwright test \
  --config=playwright.config.cjs
```

The local suite uses the dev environment account from `.env.dev` by default:

- `TEST_USERNAME`, default `admin`
- `TEST_PASSWORD`, default `admin`
