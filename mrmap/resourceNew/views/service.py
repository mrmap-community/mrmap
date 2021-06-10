from MrMap.icons import get_icon, IconEnum
from job.models import Job
from main.views import SecuredCreateView, SecuredListMixin, SecuredDetailView
from resourceNew.tasks import service as service_tasks
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.filtersets.service import LayerFilterSet, FeatureTypeFilterSet, FeatureTypeElementFilterSet
from resourceNew.forms.service import RegisterServiceForm
from resourceNew.models import Service, ServiceType, Layer, FeatureType, FeatureTypeElement
from django.urls import reverse_lazy, reverse
from django.conf import settings
from django.views.generic import FormView
from django_filters.views import FilterView
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext

from resourceNew.tables.service import ServiceTable, LayerTable, FeatureTypeTable, FeatureTypeElementTable


class WmsListView(SecuredListMixin, FilterView):
    model = Service
    table_class = ServiceTable
    title = get_icon(IconEnum.WMS) + gettext(" Web Map Services")
    queryset = model.objects.for_table_view(service_type__name=OGCServiceEnum.WMS)

    def get_table_kwargs(self):
        return {
            'exclude': ('feature_types_count',)
        }


class WfsListView(SecuredListMixin, FilterView):
    model = Service
    table_class = ServiceTable
    title = get_icon(IconEnum.WFS) + gettext(" Web Feature Services")
    queryset = model.objects.for_table_view(service_type__name=OGCServiceEnum.WFS)

    def get_table_kwargs(self):
        return {
            'exclude': ('layers_count',)
        }


class LayerListView(SecuredListMixin, FilterView):
    model = Layer
    table_class = LayerTable
    filterset_class = LayerFilterSet
    queryset = model.objects.for_table_view()


class FeatureTypeListView(SecuredListMixin, FilterView):
    model = FeatureType
    table_class = FeatureTypeTable
    filterset_class = FeatureTypeFilterSet
    queryset = model.objects.for_table_view()


class FeatureTypeElementListView(SecuredListMixin, FilterView):
    model = FeatureTypeElement
    table_class = FeatureTypeElementTable
    filterset_class = FeatureTypeElementFilterSet
    queryset = model.objects.for_table_view()


class ServiceTreeView(SecuredDetailView):
    model = Service
    template_name = 'generic_views/resource.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'tree_style': True})

        if self.object.is_service_type(OGCServiceEnum.WFS):
            self.template_name = 'resourceNew/service/views/wfs_tree.html'
        elif self.object.is_service_type(OGCServiceEnum.WMS):
            context.update({"nodes": self.object.root_layer.get_descendants(include_self=True)})
            self.template_name = 'resourceNew/service/views/wms_tree.html'
        elif self.object.is_service_type(OGCServiceEnum.CSW):
            self.template_name = 'resourceNew/service/views/csw.html'
            # todo

        return context


class RegisterServiceFormView(FormView):
    model = Service
    form_class = RegisterServiceForm
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = 'Async task was created to create new resource.'
    success_url = reverse_lazy('resource:pending-tasks')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        cleaned_data.update({"registering_for_organization": cleaned_data["registering_for_organization"].pk})
        job_pk = service_tasks.register_service(
                        form.cleaned_data,
                        **{"created_by_user_pk": self.request.user.pk,
                           "owned_by_org_pk": form.cleaned_data["registering_for_organization"]})
        try:
            job = Job.objects.get(pk=job_pk)
            self.success_url = job.get_absolute_url()
        except Job.ObjectDoesNotExist:
            pass
        return super().form_valid(form=form)
