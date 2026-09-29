# MrMap

MrMap is a Django + React application.

## Backend

- Django
- Django REST Framework
- rest_framework_json_api which implements: json:api standard v1.1 https://jsonapi.org/format/
- drf-spectacular
- PostgreSQL/PostGIS

Backend code is primarily under:
`backend/`

## Frontend

- React
- TypeScript
- React-Admin
- Material UI

Frontend code is primarily under:
`frontend/src/`

## Development guidelines

- Prefer existing React-Admin abstractions over custom implementations.
- Use MUI components for UI.
- Keep TypeScript types strict.
- Follow existing project patterns before introducing new abstractions.
- Do not change API contracts unless explicitly requested.
- Run relevant tests after modifications.