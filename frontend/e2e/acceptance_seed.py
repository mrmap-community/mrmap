# Deterministic seed for the #1034 browser acceptance stack.
#
# Runs against the development database of the acceptance stack, from the
# repository root, e.g.:
#
#   docker compose exec -T backend \
#     python manage.py shell -c "$(cat frontend/e2e/acceptance_seed.py)"
#
# It loads the repository's own behave fixtures (the same deterministic rows
# the Gherkin suite pins by PK), creates the dedicated login user and gives
# the dataset records the three geometry shapes of #947: valid, EMPTY, absent.

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Polygon

# 0) the acceptance database is disposable: flush makes the seed rerunnable
call_command("flush", interactive=False, verbosity=0)

# 1) the repo's own deterministic fixtures: users, the WMS service with its
#    layer tree, the CSW service the dataset relations point at, and two
#    dataset metadata records (PKs pinned by the behave suite as well)
for fixture in ("test_users", "test_keywords", "test_crs", "test_csw", "test_wms",
                "test_datasetmetadata"):
    print("LOADING", fixture)
    call_command("loaddata", fixture, verbosity=0)

# 2) dedicated login user for the acceptance run (this stack only, not a real
#    credential): superuser sees every record through the audited break-glass
#    of decision Q6=A
User = get_user_model()
if not User.objects.filter(username="acceptance").exists():
    User.objects.create_superuser(username="acceptance", email="acceptance@example.invalid",
                                  password="Acceptance-e2e")

# 3) make WMS1 reachable inside the stack so the viewer and the preview get
#    real GetMap answers from the compose mapserver
from registry.models.service import WebMapService, Layer
WMS_URL = "http://mrmap-mapserver/cgi-bin/mapserv?map=/etc/mapserver/mapfiles/wfs_test_data.map"
WebMapService.objects.filter(pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3").update(service_url=WMS_URL)
Layer.objects.filter(service__pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3").update(is_active=True)

# 4) dataset geometries for #947: one valid, one EMPTY, one absent (a copy of
#    the valid row with its own identifiers - the unique together of
#    file_identifier/code/code_space forbids duplicating them)
from registry.models.metadata import DatasetMetadataRecord
valid = MultiPolygon(Polygon.from_bbox((6.0, 47.0, 15.0, 55.0)), srid=4326)
DatasetMetadataRecord.objects.filter(pk="d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4").update(
    bounding_geometry=valid)
empty = MultiPolygon(srid=4326)
DatasetMetadataRecord.objects.filter(pk="9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e").update(
    bounding_geometry=empty, title="Relative Feuchte an RBSN Stationen (empty geometry)")
row = DatasetMetadataRecord.objects.get(pk="d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4")
row.pk = None
row.title = "E2E Dataset Without Geometry"
row.record_name = "e2e-dataset-without-geometry"
row.file_identifier = "e2e-dataset-without-geometry-id"
row.code = "e2e-dataset-without-geometry"
row.bounding_geometry = None
row.save()

print("SEED-OK",
      "users:", User.objects.count(),
      "wms:", WebMapService.objects.count(),
      "datasets:", DatasetMetadataRecord.objects.count())
