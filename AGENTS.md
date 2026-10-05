# MrMap

MrMap is a web application with a Django backend and a React/TypeScript frontend.

## Project structure

- `backend/` — Django backend
- `frontend/src/` — React frontend

Before implementing changes, inspect the surrounding code and existing project patterns. Prefer extending existing abstractions over introducing new ones.

Backend conventions and test commands are documented in `backend/AGENTS.md`. Read that file before modifying backend code.

## Frontend

The frontend uses:

- React
- TypeScript
- React-Admin
- Material UI (MUI)

When working on frontend code:

- Prefer React-Admin abstractions and hooks over custom implementations.
- Prefer MUI components and styling APIs over custom HTML/CSS.
- Keep TypeScript types strict; avoid `any` unless there is a strong reason.
- Reuse existing project components, hooks, utilities, and patterns.
- Follow existing routing and resource conventions.
- Preserve existing API contracts and JSON:API behavior.

## Development guidelines

### General

- Make the smallest change necessary to solve the requested problem.
- Do not refactor unrelated code.
- Follow the style and architecture of the surrounding code.
- Reuse existing abstractions before creating new ones.
- Avoid adding dependencies unless necessary.
- Preserve backwards compatibility unless explicitly instructed otherwise.
- Do not silently change behavior outside the requested scope.

### Before modifying code

1. Inspect the relevant files and surrounding implementation.
2. Search the codebase for similar implementations.
3. Identify existing utilities, components, managers, querysets, or abstractions that can be reused.
4. Consider backend/frontend interactions before changing API-facing behavior.

### Verification

After modifications:

- Run the most relevant existing tests.
- Run type checking, linting, or formatting checks when applicable.
- Add or update tests when behavior changes.
- Do not modify tests merely to make an incorrect implementation pass.
- Report any tests or checks that could not be run.

## Working with uncertainty

If requirements are ambiguous, prefer behavior consistent with the existing codebase.

Do not invent APIs, models, fields, components, or project conventions. Inspect the implementation first.

If a requested change would require a significant architectural change, API contract change, or database migration that was not explicitly requested, explain the implication before proceeding.

## Common commands

The project uses dedicated Docker containers for running tests. Prefer the test containers instead of running test commands directly in the application containers.

### Frontend

Run frontend commands from `frontend/`.

Install dependencies:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

Use the scripts defined in `frontend/package.json` for linting, type checking, testing, and building. Do not assume a script exists without checking `package.json`.

For cross-stack changes, verify both backend and frontend. Prefer targeted tests during development; run broader suites when the scope or risk warrants it.
