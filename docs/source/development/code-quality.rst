.. _development-code-quality:

Code quality
============

Quality checks run locally through VS Code tasks and in GitHub Actions. No Sonar server or
external coverage account is required. The authoritative configurations are
``frontend/eslint.config.mjs``, ``frontend/tsconfig.json``, ``frontend/vite.config.mjs``,
``backend/setup.cfg`` and ``.github/workflows/quality-assurance.yml``.

Editor feedback
---------------

Install the workspace extension recommendations and select the project Python environment.
See :ref:`development-vscode-cfg` for save actions and Docker-only editor setup.
Flake8 checks Python; autopep8 formats it. ESLint checks frontend code and owns import sorting.
TypeScript checks remain strict. Formatting cannot fix every lint or type error.

Frontend checks
---------------

Run these commands from the repository root, after configuring the development environment
files described in :ref:`development`:

.. code-block:: bash

   # Initialize or refresh the dedicated dependency volume after lockfile changes.
   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm frontend-tests npm ci --no-audit --no-fund
   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm frontend-tests npm run lint
   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm frontend-tests npm run type-check
   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm frontend-tests npm run test-coverage

``lint`` is read-only. Use ``lint:fix`` to apply ESLint fixes deliberately, preferably with a
specific file path through ``npx eslint --fix <path>`` during scoped work. ``format`` rewrites
files with Prettier and is separate from the required checks.

Vitest includes untested application files in coverage, excludes specs, fixtures and type
declarations, and writes ``frontend/coverage/index.html``, ``lcov.info`` and
``coverage-summary.json``. CI publishes the directory as the ``frontend-coverage`` artifact
and writes the totals into the workflow summary, including when a test fails.

The initial coverage floors are 52% lines, 51% statements, 49% branches and 48% functions.
These are rollout floors below the measured baseline, not target levels for well-tested code.
Raise them as coverage improves; do not lower them to make a failing check pass. Coverage
measures execution rather than assertion quality, so meaningful tests remain required.

Backend coverage
----------------

Run backend suites sequentially: they share the same test database. Both services use the
coverage configuration in ``backend/setup.cfg`` and exclude tests, generated migrations and
``manage.py`` from measurement:

.. code-block:: bash

   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm django-tests
   docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm behave

The suites write ``backend/.coverage.unit`` and ``backend/.coverage.acceptance`` respectively,
plus separate XML reports. Both data files must be collected from the same checkout. Do not
average their coverage percentages or combine reports from different source revisions.

To combine and inspect the results without rerunning Django or requiring host GDAL:

.. code-block:: bash

   cd backend
   ../.venv/bin/python -m coverage combine --keep .coverage.unit .coverage.acceptance
   ../.venv/bin/python -m coverage xml
   ../.venv/bin/python -m coverage html
   ../.venv/bin/python -m coverage report --fail-under=75

Coverage.py is already pinned in the development requirements. This reporting command can also
run in the backend test image by overriding its command. HTML is written to
``backend/coverage/html/index.html`` and combined XML to ``backend/coverage/coverage.xml``.
CI combines only artifacts from its own workflow run, publishes ``backend-coverage`` and gates
on 75% of the combined statement and branch opportunities (Coverage.py's total). This is
not a separate 75% line or branch threshold.

Static security analysis
------------------------

``.github/workflows/codeql.yml`` scans Python and JavaScript/TypeScript using CodeQL's
``security-extended`` queries on pull requests, branch pushes and a weekly schedule. It does
not need to start the application. Findings appear in GitHub code scanning after the workflow
runs. Code scanning must be available/enabled for the repository; avoid enabling GitHub's
separate default setup alongside this advanced workflow.

Repository settings
-------------------

The workflow checks fail on errors. To enforce them at merge time, maintainers must add the
quality jobs as required status checks in the branch ruleset after their first successful run.
Workflow files alone do not configure branch protection. CodeQL alert severities can also be
enforced through repository rulesets.

The reports can later be uploaded to Codecov for changed-line coverage and trends, or imported
into SonarQube Cloud for a unified dashboard. Neither integration is needed for the current
local and CI checks, and no external service credentials are configured here.
