# MrMap backend

Django / Django REST Framework backend using `rest_framework_json_api`,
`drf-spectacular`, PostgreSQL/PostGIS, django-simple-history, Celery and Django Channels.

Paths in this file are relative to `backend/`. The internals of the `registry` monolith are
described in `registry/AGENTS.md`.

## Architecture

Business logic should generally live in:

- model methods (`registry/models/`)
- QuerySets and managers (`registry/querys/`, `registry/managers/`)
- mapping and persistence classes (`registry/mappers/`)
- Celery tasks for long-running work (`registry/tasks/`)

Keep ViewSets and serializers thin. Put cross-app generic code in `extras/`
(`viewsets.py`, `permissions.py`, `schema.py`, `fields.py`, `managers.py`, `decorators.py`) instead
of duplicating it.


## Code navigation

`registry/` is the monolith holding the service registry; see `registry/AGENTS.md` for its
internals.

| Path | Contents |
| --- | --- |
| `registry/models/` | Models and lifecycle behavior |
| `registry/managers/`, `registry/querys/` | Managers and querysets (`querys/` spelling is intentional) |
| `registry/filters/`, `registry/serializers/`, `registry/views/` | API filtering, serialization, viewsets |
| `registry/mappers/` | Capabilities parsing, mapping and persistence per protocol version |
| `registry/tasks/` | Celery tasks: service build, harvesting, updates, monitoring |
| `registry/ows_lib/`, `registry/views_ows/`, `registry/proxy/` | OWS domain code, OWS endpoints, security proxy |
| `registry/helper/`, `registry/expressions/`, `registry/enums/` | Shared helpers, SQL/ORM expressions, enums |
| `notify/` | Background processes and WebSocket notifications (Channels consumers, routing, signals) |
| `accounts/` | Users, groups and guardian object permissions |
| `system/` | System status, status logging, periodic task scheduler |
| `extras/` | Shared DRF base classes, permissions, schema helpers, fields, managers, decorators |
| `csw/`, `mapbender_compatibility/` | OGC CSW endpoint, legacy MapBender endpoints |
| `MrMap/` | Project root: `settings.py`, `urls.py`, `celery.py`, `asgi.py` |
| `tests/django/` | Django unit tests, mirroring the app layout |
| `tests/behave/features/` | Acceptance scenarios (Gherkin) for API and workflow behavior |

Inspect the corresponding model, queryset, filter, serializer, viewset, and
relevant tests before changing API behavior. Follow existing abstractions and
naming, including `querys/`.

## API behavior

- Preserve JSON:API 1.1 resource types, relationships, filter names, pagination, errors, and response structure.
- Keep schema declarations compatible with `drf-spectacular`.
- Preserve permission checks and queryset visibility rules.
- Check frontend usage before changing API-facing behavior.
- Do not change API contracts unless explicitly requested.

## Queries, database and model lifecycle

- Put reusable database selection logic in existing querysets/managers (`registry/querys/`,
  `registry/managers/`, shared mixins in `extras/managers.py`).
- Prefer ORM filtering and database-side annotations over Python-side processing when practical.
- Avoid unnecessary queries and N+1 patterns; reuse existing `select_related`/`prefetch_related` helpers.
- Keep querysets lazy unless evaluation is required.
- Models using django-simple-history must preserve history, also during bulk operations and
  deletion; inspect existing history managers and signals before changing these paths. Bulk writes
  keep history through
  `simple_history.utils.bulk_create_with_history` and `bulk_update_with_history`, used in
  `registry/mappers/persistence/handler.py` and `registry/models/update.py`.
- For service update changes, verify candidate and published-service behavior, including child objects and history. See `tests/django/registry/tests_update_candidates.py`.
- Create migrations only when the requested change requires a database schema change, and run the
  migration check described under "Pre-submit checks" before handing the change back.

## Verification and commands

Run Docker commands from the repository root. Test services are defined in
`docker-compose.dev.yml`; combine it with `docker-compose.yml`, as the existing
IDE tasks do. Commands require the project's configured environment files and Docker.

Full Django suite (uses the service's coverage command):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests
```

Targeted Django tests (overrides the default coverage command). A label can be a dotted module path
or a path on disk:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests python manage.py test tests.django.registry.tests_update_candidates --noinput
```

Use the path form for directories that cannot be imported as modules, for example the hyphenated
`tests/django/registry/mrmap-proxy`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests python manage.py test tests/django/registry/mrmap-proxy --noinput
```

API/workflow integration suite:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave
```

Targeted Behave scenarios. Quote the feature path: most features live below
`tests/behave/features/json:api/` and the colon breaks unquoted arguments. Only the `@skip` tag is
used, which the service command excludes with `--tags=-skip`.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave /bin/sh -c "python manage.py behave --simple --noinput --no-skipped 'tests/behave/features/json:api/registry/service/wms'"
```

### Pre-submit checks

CI runs `backend/.bash_scripts/pre_commit_check.sh` in the `pre-commit-check` service. It gates on
flake8, model/migration drift and the translation checks below, so run it before reporting a task as
done:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pre-commit-check /bin/sh -c "/opt/mrmap/.bash_scripts/pre_commit_check.sh"
```

Targeted flake8 with the CI settings. The project configures no Python formatter, only flake8 and
autopep8 in `.requirements/dev.txt`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pre-commit-check flake8 --ignore E501,W503,W504 registry/models/service.py
```

### Test and command rules

- Backend implementation changes: run relevant Django tests first.
- API/workflow changes: also run relevant Behave scenarios. Inspect existing feature files and the service command before choosing a targeted command.
- Follow existing Django `TestCase`, fixtures, and `APIRequestFactory` patterns where applicable.
- Test modules are named `test_*.py` under `tests/django/notify` and `tests/django/system` and
  `tests_*.py` under `tests/django/registry`; follow the convention of the folder you edit.
- Run Django management commands in the `backend` application service using the development Compose configuration. Its image entrypoint waits for the database and applies migrations when the hostname contains `backend`, so a one-off `run --rm backend python manage.py ...` migrates before running the command.
- Before creating migrations, verify that the requested change requires them.
- Report commands run, results, and any checks that could not run.

## Translations

Backend strings are translated through Django's gettext toolchain in `locale/de/`. Adding or
changing a translatable string triggers a workflow enforced by the `pre-commit-check` CI job:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend python manage.py makemessages --locale=de
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend python manage.py compilemessages --locale=de
```

- Fill every new `msgstr` in `locale/de/LC_MESSAGES/django.po`; empty translations fail CI.
- Both `django.po` and `django.mo` are committed and must stay in sync with the code.
- Frontend translations are separate and live in `frontend/src/i18n/`.


## Feature specifications

Application behavior is specified using Cucumber/Behave.

Feature files are located under:

    tests/behave/features/

Treat existing feature scenarios as authoritative descriptions of
expected application behavior.

When implementing new user-visible behavior:

1. Look for an existing feature covering the behavior.
2. Update or add scenarios when requirements change.
3. Implement the change.
4. Run the affected scenarios.