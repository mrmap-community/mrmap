"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""

from django.db import transaction
from django.http import HttpResponseRedirect, HttpResponse
from django.views.generic import DetailView
from django_filters.views import FilterView

from extras.views import SecuredCreateView, SecuredListMixin, SecuredDeleteView
from jobs.models import Job
from registry.filtersets.conformity import ConformityCheckRunFilterSet
from registry.forms.conformity import ConformityCheckRunModelForm
from registry.models.conformity import ConformityCheckRun
from registry.tables.conformity import ConformityCheckRunTable
from registry.tasks import run_conformity_check


class ConformityCheckRunListView(SecuredListMixin, FilterView):
    model = ConformityCheckRun
    table_class = ConformityCheckRunTable
    filterset_class = ConformityCheckRunFilterSet
    queryset = ConformityCheckRun.objects.select_related("config", "service", "service__service_type",
                                                         "service__metadata", "layer", "layer__metadata",
                                                         "feature_type", "feature_type__metadata",
                                                         "dataset_metadata", "service_metadata", "layer_metadata",
                                                         "feature_type_metadata",
                                                         "owned_by_org")


class ConformityCheckRunCreateView(SecuredCreateView):
    model = ConformityCheckRun
    form_class = ConformityCheckRunModelForm

    def form_valid(self, form):
        response = super().form_valid(form)
        transaction.commit()
        resource = None
        for fk_field in self.model._resource.fk_fields:
            resource = resource or form.cleaned_data[fk_field]
        org_pk = resource.owned_by_org_id
        job_pk = run_conformity_check(self.object.pk, created_by_user_pk=self.request.user.pk, owned_by_org_pk=org_pk)
        try:
            job = Job.objects.get(pk=job_pk)
            return HttpResponseRedirect(job.get_absolute_url())
        except Job.ObjectDoesNotExist:
            pass
        return response


class ConformityCheckRunDeleteView(SecuredDeleteView):
    model = ConformityCheckRun


class ConformityCheckRunReportView(DetailView):
    model = ConformityCheckRun
    queryset = ConformityCheckRun.objects.only('report', 'report_type')

    def render_to_response(self, context, **kwargs):
        content_type = self.object.report_type or 'text/plain'
        content = self.object.report or 'Report is missing'
        return HttpResponse(content, content_type)