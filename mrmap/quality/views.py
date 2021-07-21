"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from rest_framework import status

from main.views import SecuredCreateView
from quality.models import ConformityCheckRun, ConformityCheckConfiguration
from quality.tasks import run_quality_check, complete_validation, \
    complete_validation_error
from resourceNew.models import DatasetMetadata
from resourceNew.views.metadata import DatasetMetadataListView

CURRENT_VIEW_QUERY_Param = 'current-view'
CURRENT_VIEW_ARG_QUERY_Param = 'current-view-arg'


class ConformityCheckRunCreateView(SecuredCreateView):
    model = ConformityCheckRun
    queryset = ConformityCheckRun.objects.all()

    # user= None
    # @permission_required(PermissionEnum.CAN_RUN_VALIDATION, raise_exception=True)

    def dispatch(self, request, *args, **kwargs):
        # TODO
        #config_id = request.GET.get('config_id', None)
        metadata_id = kwargs.get('metadata_id', None)
        user_id = request.user.pk

        if metadata_id is None:
            return HttpResponse('Parameter metadata_id is missing', status=status.HTTP_400_BAD_REQUEST)

        ccr = ConformityCheckRun()
        # TODO fetch correct config by id instead of first one
        ccr.conformity_check_configuration = ConformityCheckConfiguration.objects.get_for_metadata_type(
            'dataset').first()
        config_id = ccr.conformity_check_configuration.id
        ccr.metadata = DatasetMetadata.objects.filter(pk=metadata_id).first()
        ccr.save()

        success_callback = complete_validation.s()
        error_callback = complete_validation_error.s(user_id=user_id,
                                                     config_id=config_id,
                                                     metadata_id=metadata_id)
        run_quality_check.apply_async(args=(config_id, metadata_id),
                                      link=success_callback,
                                      link_error=error_callback)

        return HttpResponseRedirect(reverse("resourceNew:dataset_metadata_list"), status=303)

# TODO is this still needed?
# def get_latest(request, metadata_id: str):
#     metadata = get_object_or_404(Metadata, pk=metadata_id)
#
#     try:
#         latest_run = ConformityCheckRun.objects.get_latest_check(metadata)
#         latest = {
#             "passed": latest_run.passed,
#             "running": latest_run.is_running(),
#         }
#     except ConformityCheckRun.DoesNotExist:
#         latest = {
#             "passed": None,
#             "running": None,
#         }
#
#     return JsonResponse(latest)
