# registry app

The spatial service registry of MrMap and the largest Django app in the project. It handles OGC
services (WMS, WFS, CSW), their metadata, harvesting, update jobs, monitoring and the security
proxy.

Paths in this file are relative to `backend/registry/`. Backend-wide rules and commands stay in
`backend/AGENTS.md`; this file only adds registry specific detail.

## Layout

| Path | Responsibility |
| --- | --- |
| `models/` | Models and their lifecycle behaviour. `service.py` holds the OGC service aggregate. |
| `managers/` | Default managers, one module per aggregate. |
| `querys/` | QuerySet classes. The folder is spelled `querys/`, not `querysets/`; keep the name. |
| `filters/` | `django-filter` FilterSets exposed through the API. |
| `serializers/` | JSON:API serializers per aggregate. |
| `views/` | API viewsets. `views_ows/` holds the OWS map context endpoints. |
| `mappers/` | Capabilities mapping and persistence: `configs/` per protocol version, `parsers/`, `persistence/`, `factory.py`, `xml_mapper.py`, `identifiers.py`, `cache.py`. |
| `ows_lib/` | OWS domain code: `client/`, `request/`, `response/`, `xml/`, `wms/`, `wfs/`, `csw/`. No DRF or model code. |
| `proxy/` | Security proxy for secured services (`wms_proxy.py`, `wfs_proxy.py`, `mixins.py`). |
| `tasks/` | Celery tasks: service building, harvesting and recovery, updates, monitoring, conformity, security. |
| `helper/` | Mapping helpers plus `plugins/` (`etf.py`, `internal.py`) for external validation. |
| `expressions/` | Reusable ORM/SQL expressions, e.g. `layer_ctes.py` for partitioned layer queries. |
| `enums/` | Enumerations per aggregate. |
| `admin/`, `fixtures/`, `migrations/`, `templates/` | Django admin, fixtures, schema history, templates. |

## Where behaviour lives

- Registration and update flows are orchestrated in `tasks/`, parsed and persisted in `mappers/`,
  guarded by invariants in `models/`; `views/` and `serializers/` stay thin.
- Protocol version differences are declarative: `mappers/configs/wms111.py`, `wms130.py`,
  `wfs200.py`, `csw202.py`, `dataset.py`. Add a version by adding a config, not by branching in
  shared code.
- Bulk persistence mode is also configuration: `"_create_mode": "bulk_with_history"` is handled in
  `mappers/persistence/handler.py` with `simple_history.utils.bulk_create_with_history`, so history
  is preserved for bulk writes.
- Bulk history updates use `simple_history.utils.bulk_update_with_history`
  (see `models/update.py`).
- Shared manager behaviour lives in `backend/extras/managers.py`, e.g. `with_history()` which
  prefetches the last two historical records for delta calculation.

## Tests

- Unit tests mirror this layout below `backend/tests/django/registry/` (`models/`, `managers/`,
  `tasks/`, `ows_lib/`, `mrmap-proxy/`) and are named `tests_*.py` in this app.
- Acceptance scenarios live in `backend/tests/behave/features/json:api/registry/`; treat them as the
  specification of the API behaviour you are changing.
