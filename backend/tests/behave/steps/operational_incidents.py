"""Domain steps of the operational incident scenarios (#1319).

The incidents of these scenarios are created by the steps, not by a fixture:
an incident row is the answer of a reporter (the publishers of #1320 will be
the first producers in production), and a scenario reads most clearly when
it reports the incident it wants to read. The WMS behind them is the first
service of ``test_wms.json``, the same service ``object_permissions.py``
grants upon.
"""
from behave import given
from guardian.shortcuts import assign_perm
from notify.enums import IncidentSeverityEnum, IncidentSourceEnum
from notify.models import OperationalIncident
from registry.models.service import WebMapService

#: the first WMS of ``test_wms.json``
SERVICE_ID = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

#: the list url of the incident api, as the features address it
LIST_URL = "http://localhost:8000/api/notify/operational-incidents"


@given('an incident "{code}" stands for the WMS of the feature')
def create_incident_for_the_wms(context, code):
    OperationalIncident.objects.report(
        code=code,
        source=IncidentSourceEnum.MONITORING.value,
        severity=IncidentSeverityEnum.WARNING.value,
        summary=f"the reported problem {code} of the WMS",
        resource={"web_map_service": WebMapService.objects.get(
            pk=SERVICE_ID)})


# The existence of an incident the caller may not view is itself protected
# (#1319): only the detail url answers the question, so the step which
# reports the incident also points the scenario's request at its detail.
@given('an incident "{code}" stands for the WMS of the feature and its detail is requested')
def report_incident_and_request_its_detail(context, code):
    incident, _ = OperationalIncident.objects.report(
        code=code,
        source=IncidentSourceEnum.MONITORING.value,
        severity=IncidentSeverityEnum.WARNING.value,
        summary=f"the reported problem {code} of the WMS",
        resource={"web_map_service": WebMapService.objects.get(
            pk=SERVICE_ID)})
    context.endpoint = f"{LIST_URL}/{incident.pk}"


@given('an incident "{code}" stands for the WMS and is resolved')
def create_resolved_incident_for_the_wms(context, code):
    incident, _ = OperationalIncident.objects.report(
        code=code,
        source=IncidentSourceEnum.MONITORING.value,
        severity=IncidentSeverityEnum.ERROR.value,
        summary=f"the reported problem {code} of the WMS",
        resource={"web_map_service": WebMapService.objects.get(
            pk=SERVICE_ID)})
    OperationalIncident.objects.resolve(incident.dedup_key)


@given('a system incident "{code}" stands')
def create_system_incident(context, code):
    OperationalIncident.objects.report(
        code=code,
        source=IncidentSourceEnum.SYSTEM.value,
        severity=IncidentSeverityEnum.ERROR.value,
        summary=f"the deployment problem {code}",
        details={"queue": "import"})


@given('the user "{username}" may view the WMS of the feature')
def grant_view_permission_on_the_wms(context, username):
    from django.contrib.auth import get_user_model
    assign_perm("registry.view_webmapservice",
                get_user_model().objects.get(username=username),
                WebMapService.objects.get(pk=SERVICE_ID))
