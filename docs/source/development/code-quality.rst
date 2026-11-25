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

Local Git hooks
---------------

Enable the tracked hooks once from the repository root (Python 3 and Git are required):

.. code-block:: bash

   python3 scripts/git_checks.py install

The installer puts executable wrappers in Git's hooks directory, which is shared by linked
worktrees. It refuses to overwrite custom hooks or redirect an existing ``core.hooksPath``;
integrate the tracked wrappers manually if you already have either setup. Re-running the
installer updates only MrMap's wrappers. Remove them with ``python3 scripts/git_checks.py uninstall``.
The checks themselves live in ``scripts/git_checks.py`` and follow the checked-out branch;
no hook framework or tracked executable-bit changes are needed. On older branches without
that runner, the wrappers print a skip message so other worktrees can still commit and push.

``pre-commit`` lints changed, staged backend Python and frontend JavaScript/TypeScript files.
It uses the existing Flake8 and ESLint configurations; changing a lint configuration or its
dependency manifest runs the corresponding full lint. Backend tests retain the existing CI
Flake8 exclusion. An available ``.venv/bin/flake8`` or ``flake8`` on ``PATH`` avoids Docker for
Python lint; frontend lint and the Python fallback use the existing dependency images.

``pre-push`` runs the existing backend pre-submit check (lint, migration drift and translations)
when backend files changed, and frontend lint, strict type checking and translation tests when frontend files
changed. Deletions and renames count as changes. Documentation-only changes skip application
checks and do not start Docker. The optional agent Sonar setup below adds static analysis before
pushing. Full tests and coverage remain in CI; run relevant tests locally as described below.
Hooks can be bypassed, so they do not replace required CI checks.

Checks run on a temporary export of the index or the actual pushed tree, including when a ref
other than the checked-out branch is pushed. Partially staged edits and working files are left
untouched. Existing remote refs are compared with the remote object Git supplies. A new ref uses
the merge base with the fetched remote default branch (or ``<remote>/develop``); without that
baseline, its entire tree is checked. Fetch the remote if a comparison object is missing.
Deleted remote refs need no checks. Each updated ref is checked separately.

Docker checks require the usual ``.env`` and ``docker/backend/.mrmap.env`` in this checkout.
Prepare the immutable dependency images before the first code check, and again after dependency
changes, using the resolver described in :doc:`prebuilt-images`:

.. code-block:: bash

   python3 scripts/dev_image_id.py --resolve --image backend --build
   python3 scripts/dev_image_id.py --resolve --image frontend --build

Hooks reuse or pull matching images; they never build an image or install host Node/GDAL.
Every invocation requires external admission before starting Docker, creates a separate
Compose project with no published dependency ports, and removes its containers, networks and
volumes afterwards, including on failure or interruption. Cached images remain available.
The frontend image seeds its disposable dependency volume, so no ``npm ci`` is needed for each
check. Hooks do not use or restart the developer's services. Missing prerequisites and failed
checks stop the Git operation with an error.

To invoke the commit checks directly, run ``python3 scripts/git_checks.py commit``. Push checks
read Git's ref-update records from standard input and normally run through ``git push``.
The offline hook regression suite is ``python3 scripts/test_git_checks.py`` and is included in
``scripts/check_repo_tooling.sh``.

Agent Sonar setup
~~~~~~~~~~~~~~~~~

Provision the official `SonarScanner CLI
<https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/scanners/sonarscanner-cli>`_
on the agent's ``PATH`` through the external agent bootstrap. The launcher or secret manager
must inject ``SONAR_TOKEN`` into the agent process environment. The token needs Execute Analysis
permission on the existing SonarQube Cloud project. Do not put it in Git, a tracked environment
file, a command argument or the agent's chat. GitHub Actions secrets cannot be read back for local use.

With the token already injected, enable the agent hooks once per checkout:

.. code-block:: bash

   # The launcher has already injected SONAR_TOKEN into this process environment.
   sonar-scanner --version
   python3 scripts/git_checks.py install --sonar

Setup checks for the token, scanner and full Git history before installing. It stores only
``mrmap.sonarPrePush=true`` in the local Git configuration, shared by linked worktrees. Every
subsequent branch push with application changes requires a token and scanner; missing credentials,
scanner failures, timeouts and a failing static quality gate stop the push. Documentation-only
updates and remote ref deletions need no scan. Uninstalling the managed hooks clears the requirement.
The presence of ``SONAR_TOKEN`` also enables scanning without the persisted requirement.

The defaults are organization ``mrmap-community``, project ``mrmap-community_mrmap`` and target
branch ``develop``. Set ``SONAR_ORGANIZATION``, ``SONAR_PROJECT_KEY`` or ``SONAR_TARGET_BRANCH`` in
the launcher if those differ. These identifiers are public; the token stays in the environment
and is never saved by the hooks. Setup does not create a token or change project permissions.

After the ordinary pre-push checks succeed, SonarScanner analyzes a temporary local clone of the
actual pushed commit with its Git history. The existing ``sonar-project.properties`` supplies
the analysis scope. Results are sent to a separate ``pre-push/<destination-branch>`` branch in
SonarQube Cloud, targeted at ``SONAR_TARGET_BRANCH``; the scanner waits up to 300 seconds for its
quality gate. This requires branch analysis support and an existing target-branch analysis.
The temporary clone is removed after success, failure or interruption.

This is a static preflight, not the full CI gate: source files are excluded from coverage only
for this separate preview analysis, because the quick checks do not generate full-suite reports.
Static rules and duplication remain checked. The real branch and PR results, their coverage
thresholds and the CI workflow are untouched. A code push therefore also needs the full CI
analysis before merging. API-created commits do not invoke Git hooks; an agent publishing through
an API must run the pre-push runner explicitly with Git's ref-update input before publishing.

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

Frontend translation tests run with ``npm run test -- --run src/i18n`` in ``frontend-tests``.
They check matching English/German keys, non-empty strings and consistent ``%{placeholder}``
names for all MrMap application messages. React-Admin's built-in ``ra`` catalog is separate;
it includes framework defaults and intentionally blank options. The same tests run in the
pre-push hook for frontend changes and in the existing CI frontend suite.

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

For feedback before pushing, install the recommended SonarQube for IDE extension and configure
its connected mode to bind this workspace to the ``mrmap-community_mrmap`` SonarQube Cloud
project. Keep authentication tokens in the extension's credential storage. Connected mode
synchronizes the project's quality profile, but not every server-side analysis can run locally;
see the `supported rules documentation
<https://docs.sonarsource.com/sonarqube-for-vs-code/using/rules>`_. The Git hooks do not submit
SonarCloud analyses unless the agent Sonar setup above is enabled. The CI analysis remains the
full quality gate including coverage.

Coverage reports contain paths relative to ``backend/`` and ``frontend/``. The analysis job
adjusts only its downloaded copies so those paths resolve from the repository root: the lcov
``SF:`` records gain the ``frontend/`` prefix, and in the cobertura report every
``<class filename>`` attribute gains the ``backend/`` prefix while its ``<sources>`` element is
dropped. The python coverage sensor keeps a file name that resolves below exactly one base
directory and discards ambiguous ones, so announcing the same directory twice costs the whole
python coverage without failing the job - see issue #757. The adjusted entries are checked
against the checkout and the job fails when one of them does not exist. The
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
   The README badge uses the historical project key ``mrmap-community_mrmap``; update
   its image and dashboard URLs if the imported project's key differs.
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

Findings that are false positives for a reason visible in the source are suppressed in place with
a ``NOSONAR`` comment that states that reason, for example the normative ``http`` namespace
identifiers of the ISO, OGC, INSPIRE and GDI-DE schemas and the ``::4326`` suffix of the
``urn:ogc:def:crs:EPSG::4326`` CRS identifier. The comment goes on the reported line, names the
identifier or context it refers to and keeps the justification with the code instead of only in the
SonarCloud issue history, where it is lost as soon as the file is analyzed again. Remove such a
comment when the annotated code changes. Suppressions that hide a genuine finding are a quality
gate failure, not a fix: resolve those in the report or change the code.

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
