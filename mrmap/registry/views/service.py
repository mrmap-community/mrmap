from django.db.models import ExpressionWrapper, BooleanField, Q, Count
from django.http import HttpResponse
from extra_views import UpdateWithInlinesView
from guardian.core import ObjectPermissionChecker
from MrMap.icons import get_icon, IconEnum
from jobs.models import Job
from extras.utils import camel_to_snake
from extras.views import SecuredListMixin, SecuredDetailView, SecuredUpdateView, SecuredFormView, SecuredDeleteView
from registry.formsets.service import ExternalAuthenticationInline, ProxySettingInline
from registry.tasks import service as service_tasks
from registry.enums.service import OGCServiceEnum
from registry.filtersets.service import LayerFilterSet, FeatureTypeFilterSet, FeatureTypeElementFilterSet, \
    ServiceFilterSet
from registry.forms.service import RegisterServiceForm, ServiceModelForm, LayerModelForm
from registry.models import Service, Layer, FeatureType, FeatureTypeElement
from django.urls import reverse_lazy
from django_filters.views import FilterView
from django.utils.translation import gettext
from registry.tables.service import ServiceTable, LayerTable, FeatureTypeTable, FeatureTypeElementTable


class WmsListView(SecuredListMixin, FilterView):
    model = Service
    table_class = ServiceTable
    filterset_class = ServiceFilterSet
    title = get_icon(IconEnum.WMS) + gettext(" Web Map Services")
    queryset = model.objects.for_table_view(service_type__name=OGCServiceEnum.WMS)

    def get_table_kwargs(self):
        return {
            'exclude': ('feature_types_count',)
        }


class WfsListView(SecuredListMixin, FilterView):
    model = Service
    table_class = ServiceTable
    filterset_class = ServiceFilterSet
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


class ServiceXmlView(SecuredDetailView):
    model = Service
    content_type = "application/xml"

    def render_to_response(self, context, **response_kwargs):
        return HttpResponse(content=self.object.xml.serializeDocument(),
                            content_type=self.content_type)


class ServiceWmsTreeView(SecuredDetailView):
    model = Service
    template_name = 'registry/service/views/wms_tree.html'
    queryset = Service.objects.for_tree_view(OGCServiceEnum.WMS)
    extra_context = {'tree_style': True}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        collapse = self.request.GET.get("collapse", None)
        nodes = self.object.root_layer.get_descendants(include_self=True)\
                                      .select_related("metadata")\
                                      .annotate(has_dataset_metadata=Count('dataset_metadata'))\
                                      .prefetch_related("dataset_metadata")
        if collapse:
            layers_to_collapse = Layer.objects.get(pk=collapse)\
                                              .get_ancestors(include_self=True).values_list("pk", flat=True)
            nodes = nodes.annotate(collapse=ExpressionWrapper(Q(pk__in=layers_to_collapse),
                                                              output_field=BooleanField()))
        perm_checker = ObjectPermissionChecker(self.request.user)
        perm_checker.prefetch_perms(nodes)
        context.update({"nodes": nodes,
                        "perm_checker": perm_checker})
        return context


class ServiceWfsTreeView(SecuredDetailView):
    model = Service
    template_name = 'registry/service/views/wfs_tree.html'
    queryset = Service.objects.for_tree_view(OGCServiceEnum.WFS)
    extra_context = {'tree_style': True}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        feature_types = self.object.featuretypes.all()\
                                   .annotate(has_dataset_metadata=Count('dataset_metadata'))\
                                   .prefetch_related("dataset_metadata", "elements")

        perm_checker = ObjectPermissionChecker(self.request.user)
        perm_checker.prefetch_perms(feature_types)
        context.update({"feature_types": feature_types,
                        "perm_checker": perm_checker})
        return context


class RegisterServiceFormView(SecuredFormView):
    model = Service
    action = "add"
    form_class = RegisterServiceForm
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = 'Async task was created to create new resource.'
    # FIXME: wrong success_url

    # success_url = reverse_lazy('resource:pending-tasks')

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


class ServiceActivateView(SecuredUpdateView):
    model = Service
    form_class = ServiceModelForm
    update_query_string = True


# TODO: implement a secured UpdateWithInlinesView version
class ServiceUpdateView(UpdateWithInlinesView):
    model = Service
    inlines = [ExternalAuthenticationInline, ProxySettingInline]
    form_class = ServiceModelForm
    # update_query_string = True
    template_name = "MrMap/detail_views/generic_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


class ServiceDeleteView(SecuredDeleteView):
    model = Service

    def get_success_url(self):
        model_instance = self.model()
        if self.object.service_type_name == OGCServiceEnum.WMS.value:
            return reverse_lazy(f'{model_instance._meta.app_label}:{camel_to_snake(model_instance.__class__.__name__)}_wms_list')
        elif self.object.service_type_name == OGCServiceEnum.WFS.value:
            return reverse_lazy(f'{model_instance._meta.app_label}:{camel_to_snake(model_instance.__class__.__name__)}_wfs_list')
        elif self.object.service_type_name == OGCServiceEnum.CSW.value:
            return reverse_lazy(f'{model_instance._meta.app_label}:{camel_to_snake(model_instance.__class__.__name__)}_csw_list')


class LayerUpdateView(SecuredUpdateView):
    model = Layer
    form_class = LayerModelForm
    update_query_string = True


class FeatureTypeUpdateView(SecuredUpdateView):
    model = FeatureType
    form_class = LayerModelForm
    update_query_string = True


class CswListView(SecuredListMixin, FilterView):
    model = Service
    table_class = ServiceTable
    filterset_class = ServiceFilterSet
    title = get_icon(IconEnum.CSW) + gettext(" Catalogue Web Service")
    queryset = model.objects.for_table_view(service_type__name=OGCServiceEnum.CSW)

    def get_table_kwargs(self):
        return {
            'exclude': ('layers_count', 'feature_types_count',)
        }
