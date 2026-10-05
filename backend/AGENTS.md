# MrMap backend

Django / Django REST Framework backend using `rest_framework_json_api`,
`drf-spectacular`, PostgreSQL/PostGIS, and django-simple-history.

## Code navigation

Paths below are relative to `backend/`:

- `registry/models/`: registry models and lifecycle behavior.
- `registry/managers/` and `registry/querys/`: managers and querysets.
- `registry/filters/`: API filtering.
- `registry/serializers/`: API serialization.
- `registry/views/`: API viewsets.
- `tests/django/`: Django tests.
- `tests/behave/features/`: API and workflow integration tests.

Inspect the corresponding model, queryset, filter, serializer, viewset, and
relevant tests before changing API behavior. Follow existing abstractions and
naming, including `querys/`.

## API behavior

- Preserve JSON:API 1.1 resource types, relationships, filter names, pagination, errors, and response structure.
- Keep schema declarations compatible with `drf-spectacular`.
- Preserve permission checks and queryset visibility rules.
- Check frontend usage before changing API-facing behavior.
- Do not change API contracts unless explicitly requested.

## Queries and model lifecycle

- Put reusable database selection logic in existing querysets/managers.
- Prefer ORM filtering and annotations over Python-side processing when practical.
- Avoid unnecessary queries and N+1 patterns; reuse existing `select_related`/`prefetch_related` helpers.
- Keep querysets lazy unless evaluation is required.
- Preserve history behavior during saves, bulk operations, and deletion; inspect existing history managers and signals before changing these paths.
- For service update changes, verify candidate and published-service behavior, including child objects and history. See `tests/django/registry/tests_update_candidates.py`.
- Create migrations only when the requested change requires a database schema change.

## Verification and commands

Run Docker commands from the repository root. Test services are defined in
`docker-compose.dev.yml`; combine it with `docker-compose.yml`, as the existing
IDE tasks do. Commands require the project's configured environment files and Docker.

Full Django suite (uses the service's coverage command):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests
```

Targeted Django example (overrides the default coverage command):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests python manage.py test tests.django.registry.tests_update_candidates --noinput
```

API/workflow integration suite:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave
```

- Backend implementation changes: run relevant Django tests first.
- API/workflow changes: also run relevant Behave scenarios. Inspect existing feature files and the service command before choosing a targeted command.
- Follow existing Django `TestCase`, fixtures, and `APIRequestFactory` patterns where applicable.
- Run Django management commands in the `backend` application service using the development Compose configuration; inspect its entrypoint before overriding commands.
- Before creating migrations, verify that the requested change requires them.
- Report commands run, results, and any checks that could not run.
