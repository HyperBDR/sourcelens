# Repository Guidelines

## Project Structure & Module Organization
- Core package: `agentcore_notifier/`.
- Django integration lives in `agentcore_notifier/adapters/django/`:
  - `models.py`, `admin.py`, `urls.py`, `views/` for API/admin surface.
  - `services/` for domain logic (`webhook_service.py`, `email_service.py`, merge/silence, stats, cleanup).
  - `tasks/` and `periodic_tasks.py` for Celery async workflows.
  - `migrations/` for schema history.
- Tests are in `tests/` with Django test settings in `tests/settings.py` and fixtures in `tests/conftest.py`.
- Design and provider notes are in `docs/` (for example `docs/MERGE_SILENCE_DESIGN.md`).

## Build, Test, and Development Commands
- `pip install -e ".[dev]"`: install package in editable mode with pytest tooling.
- `pytest`: run full test suite (configured by `pytest.ini`/`pyproject.toml`).
- `pytest tests/test_webhook_service.py -v`: run a focused test module while iterating.
- `pytest --cov=agentcore_notifier.adapters.django.services --cov-report=term-missing`: check service-layer coverage.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and explicit imports.
- Use `snake_case` for functions/modules/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- Keep service logic in `services/`; keep views thin and task orchestration in `tasks/`.
- Match existing test style: descriptive test names like `test_returns_none_when_no_channel`.

## Testing Guidelines
- Framework: `pytest` + `pytest-django`.
- Test discovery: files named `test_*.py` under `tests/`.
- Use `@pytest.mark.django_db` for DB-backed tests.
- Mock external network calls (for example `requests.post`) to keep tests deterministic.

## Commit & Pull Request Guidelines
- Recent history uses short, imperative, capitalized subjects (for example: `Add stats user list API...`, `Document channel/config API...`).
- Keep commit titles focused on behavior change; include docs/tests in the same PR when relevant.
- PRs should include:
  - clear summary of behavior changes,
  - linked issue/task,
  - migration notes (if models changed),
  - test evidence (`pytest` output, and coverage command when touching services).

## Architecture Notes
- Notification sending is Celery-task driven; avoid introducing direct HTTP send endpoints for dispatch paths.
- Configuration is persisted in database models (`NotifierConfig`, `NotificationChannel`), not static Django settings.
