.. _development-code-quality:

Code quality
============

Quality checks run locally through VS Code tasks and in GitHub Actions. Local checks do not
require a SonarCloud account. The authoritative configurations are
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

SonarCloud analysis
-------------------

SonarQube Cloud (formerly SonarCloud) complements the existing checks with code quality and
security findings, duplication metrics, coverage and a quality gate. Its ``sonarcloud`` job
in ``.github/workflows/quality-assurance.yml`` waits for ``backend-coverage`` and
``frontend-tests``, then downloads their artifacts from the same workflow run. It does not
rerun either test suite. ``sonar-project.properties`` defines the analysis scope and report
locations. Tests are classified separately; generated migrations, fixtures, static assets,
templates, declarations and coverage output are excluded from application analysis.

Coverage reports contain paths relative to ``backend/`` and ``frontend/``. The analysis job
adjusts only its downloaded copies so those paths resolve from the repository root. The
original artifacts and existing coverage thresholds remain unchanged.

To enable analysis, a repository administrator must:

1. Sign in at `SonarQube Cloud <https://sonarcloud.io/>`_ with GitHub and import
   ``mrmap-community/mrmap`` as a public project. Select the free **OSS plan** for the
   open-source organization and grant the SonarQube Cloud GitHub app repository access.
   See the `subscription plans documentation
   <https://docs.sonarsource.com/sonarqube-cloud/administering-sonarcloud/managing-subscription/subscription-plans>`_.
2. Set the project's main branch to ``master`` and select **GitHub Actions / CI-based
   analysis**. Disable automatic analysis, which cannot import these coverage reports and
   cannot run alongside CI-based analysis.
3. In GitHub **Settings > Secrets and variables > Actions**, create repository variables
   ``SONAR_ORGANIZATION`` and ``SONAR_PROJECT_KEY`` using the exact keys shown by SonarCloud.
   Create an analysis token with permission to analyze the project and store it as the
   repository secret ``SONAR_TOKEN``. Never commit the token. The workflow uses the EU
   SonarCloud service at ``https://sonarcloud.io``.
4. After merging the workflow, run **Quality Assurance** on ``master`` using
   ``workflow_dispatch`` to establish the initial analysis. Configure the project's new-code definition and quality gate in
   SonarCloud so new changes can be assessed against that baseline.
5. Check that Python and TypeScript coverage appear in the dashboard and that an eligible
   pull request receives SonarCloud feedback before making its checks required.

Without both repository variables, the analysis job is skipped. Once enabled, a missing or
invalid token fails analysis. Pull requests from forks and runs by Dependabot skip this job
because they do not receive the analysis secret; their existing QA and CodeQL checks still
run. The workflow uses ``pull_request`` and does not run fork code with privileged credentials.
Renovate pull requests from branches in this repository can run analysis normally.

The scanner waits for the SonarCloud quality gate and fails the job if it fails. Use a gate
focused on new code to improve quality gradually; retain the existing CI coverage floors.
For eligibility and available features, see `SonarQube for OSS
<https://www.sonarsource.com/open-source-editions/>`_.

Repository settings
-------------------

The workflow checks fail on errors. To enforce them at merge time, maintainers must add the
quality jobs as required status checks in the branch ruleset after their first successful run.
Workflow files alone do not configure branch protection. CodeQL alert severities can also be
enforced through repository rulesets.

After onboarding, the ``sonarcloud`` check can also be required for branches whose pull
requests have access to the analysis token. Do not require a SonarCloud result for fork or
Dependabot pull requests that cannot run analysis. GitHub cannot enforce the SonarCloud gate
from this configuration alone; maintainers must configure the applicable branch rules.
