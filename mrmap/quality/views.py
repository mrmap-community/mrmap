"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django_filters.views import FilterView

from main.views import SecuredCreateView, SecuredListMixin
from quality.forms import ConformityCheckRunModelForm
from quality.models import ConformityCheckRun, ConformityCheckConfiguration


class ConformityCheckRunListView(SecuredListMixin, FilterView):
    model = ConformityCheckRun
    # table_class = ExternalAuthenticationTable
    # filterset_class = ExternalAuthenticationFilterSet


class ConformityCheckRunCreateView(SecuredCreateView):
    model = ConformityCheckRun
    form_class = ConformityCheckRunModelForm

    #
    # # user= None
    # # @permission_required(PermissionEnum.CAN_RUN_VALIDATION, raise_exception=True)
    #
    # def dispatch(self, request, *args, **kwargs):
    #     run = ConformityCheckRun()
    #     run.resource_type = kwargs['resource_type']
    #     run.resource_id = kwargs['resource_id']
    #     run.created_by_user = request.user
    #     # TODO fetch correct config by id instead of first one
    #     run.conformity_check_configuration = ConformityCheckConfiguration.objects.get_for_metadata_type(
    #         run.resource_type).first()
    #     run.save()
    #     next_url = request.META.get('HTTP_REFERER') or '/'
    #     return HttpResponseRedirect(next_url)
