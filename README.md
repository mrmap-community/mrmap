# MrMap

<img src="docs/source/images/mr_map.png" alt="MrMap logo" width="200">

[![Quality assurance](https://github.com/mrmap-community/mrmap/actions/workflows/quality-assurance.yml/badge.svg?branch=master)](https://github.com/mrmap-community/mrmap/actions/workflows/quality-assurance.yml?query=branch%3Amaster)
[![CodeQL](https://github.com/mrmap-community/mrmap/actions/workflows/codeql.yml/badge.svg?branch=master)](https://github.com/mrmap-community/mrmap/actions/workflows/codeql.yml?query=branch%3Amaster)
[![SonarCloud quality gate](https://sonarcloud.io/api/project_badges/measure?project=mrmap-community_mrmap&metric=alert_status&branch=master)](https://sonarcloud.io/dashboard?id=mrmap-community_mrmap&branch=master)
[![Documentation](https://readthedocs.org/projects/mrmap/badge/?version=master)](https://mrmap.readthedocs.io/en/master/)

MrMap is an open source registry for geospatial data, metadata and OGC services,
including Web Map Services (WMS), Web Feature Services (WFS) and Catalogue Services
for the Web (CSW). It supports service discovery, metadata harvesting, scheduled
updates and availability monitoring.

The application combines a Django backend, a React/TypeScript frontend and a
PostgreSQL/PostGIS database. Docker Compose provides the application and its
supporting services.

## Code quality and coverage

The QA and CodeQL badges show the latest workflow status on `master`. The
SonarCloud badge shows its quality-gate status for `master` and links to the
project dashboard once SonarCloud is configured. Quality assurance
runs lint, strict TypeScript checks, backend unit and acceptance tests, frontend
tests, and coverage checks. CodeQL scans Python and JavaScript/TypeScript with
the `security-extended` queries.

| Check | CI requirement | Results |
| --- | --- | --- |
| Backend coverage | At least 75% combined statement and branch coverage across unit and acceptance tests (Coverage.py total) | QA run summary and `backend-coverage` artifact |
| Frontend coverage | Lines ≥52%, statements ≥51%, branches ≥49%, functions ≥48% | QA run summary and `frontend-coverage` artifact |
| Static checks | Flake8, ESLint, strict TypeScript, migration and translation checks must pass | QA job logs |
| Security analysis | CodeQL analysis for both languages | [Code scanning alerts](https://github.com/mrmap-community/mrmap/security/code-scanning) |

To see **measured coverage**, open the latest completed
[Quality Assurance run for master](https://github.com/mrmap-community/mrmap/actions/workflows/quality-assurance.yml?query=branch%3Amaster)
and read its summary. Download the coverage artifacts from that run for HTML
reports with per-file results. The percentages above are enforced minimums;
measured results are published per run. The CodeQL badge reports analysis status;
security findings are listed separately in code scanning alerts.

See the [code quality guide](docs/source/development/code-quality.rst) for local
commands, coverage configuration and merge enforcement details.

## Getting started

- [Documentation](https://mrmap.readthedocs.io/en/master/) — usage and administration.
- [Installation guide](docs/source/installation/index.rst) — Docker Compose setup and required configuration.
- [Development setup](docs/source/development/getting-started.rst) — environment setup and development workflow.
- [Architecture](docs/architecture.md) — services, update jobs, monitoring and the security proxy.

## Community and contributions

Use [GitHub Discussions](https://github.com/mrmap-community/mrmap/discussions) for
questions, help and general feedback. Report bugs and request features through
the [issue templates](https://github.com/mrmap-community/mrmap/issues/new/choose).

Read the [contributing guide](CONTRIBUTING.md) before starting work and the
[definition of done](docs/source/development/definition_of_done.rst) before
opening a pull request.

## License

See [LICENSE](LICENSE).
