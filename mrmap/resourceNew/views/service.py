from MrMap.icons import get_icon, IconEnum
from main.views import SecuredCreateView, SecuredListMixin, SecuredDetailView
from resourceNew import tasks
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.forms import RegisterServiceForm
from resourceNew.models import Service, ServiceType
from django.urls import reverse_lazy
from django.conf import settings
from django.views.generic import FormView
from django_filters.views import FilterView
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext

from resourceNew.tables.service import WmsServiceTable


class WmsIndexView(SecuredListMixin, FilterView):
    model = Service
    table_class = WmsServiceTable
    #filterset_class = OgcWmsFilter
    title = get_icon(IconEnum.WMS) + gettext(" WMS")
    queryset = model.objects.for_table_view(service_type__name=OGCServiceEnum.WMS)

    """def get_filterset_kwargs(self, *args):
        kwargs = super(WmsIndexView, self).get_filterset_kwargs(*args)
        if kwargs['data'] is None:
            kwargs['queryset'] = kwargs['queryset'].filter(service__is_root=True)
        return kwargs
    """

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(WmsIndexView, self).get_table(**kwargs)
        # whether whole services or single layers should be displayed, we have to exclude some columns
        """
        filter_by_show_layers = self.filterset.form_prefix + '-' + 'service__is_root'
        if filter_by_show_layers in self.filterset.data and self.filterset.data.get(filter_by_show_layers) == 'on':
            table.exclude = (
                'layers', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)
        else:
            table.exclude = (
                'parent_service', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)
        """
        # render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())))
        # table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table


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
        task = tasks.create_service_from_parsed_service.apply_async((form.cleaned_data,),
                                                                    kwargs={"created_by_user_pk": self.request.user.pk,
                                                                            "owned_by_org_pk": form.cleaned_data["registering_for_organization"]},
                                                                    countdown=settings.CELERY_DEFAULT_COUNTDOWN)
        # todo filter pending tasks by task id
        return super().form_valid(form=form)
