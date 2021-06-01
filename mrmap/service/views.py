import base64
import io
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import QuerySet, Q
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, QueryDict, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, DeleteView, UpdateView, CreateView
from django.views.generic.detail import BaseDetailView
from django_bootstrap_swt.components import Tag, Link, Dropdown, ListGroupItem, ListGroup, DefaultHeaderRow
from django_bootstrap_swt.enums import ButtonColorEnum
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from django_tables2.export import ExportMixin
from requests.exceptions import ReadTimeout

from MrMap.cacher import PreviewImageCacher
from MrMap.consts import *
from MrMap.decorators import log_proxy
from MrMap.forms import get_current_view_args
from MrMap.icons import IconEnum, get_icon
from MrMap.messages import SERVICE_UPDATED, \
    SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED, SERVICE_LAYER_NOT_FOUND, \
    SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT, SERVICE_CAPABILITIES_UNAVAILABLE, \
    SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE, SERVICE_SUCCESSFULLY_DELETED, SUBSCRIPTION_SUCCESSFULLY_CREATED, \
    SERVICE_ACTIVATED, SERVICE_DEACTIVATED, MAP_CONTEXT_SUCCESSFULLY_CREATED, MAP_CONTEXT_SUCCESSFULLY_EDITED, \
    MAP_CONTEXT_SUCCESSFULLY_DELETED
from csw.models import HarvestResult
from main.views import SecuredDetailView, SecuredListMixin, SecuredDeleteView, SecuredUpdateView, SecuredCreateView
from monitoring.models import HealthState
from MrMap.settings import SEMANTIC_WEB_HTML_INFORMATION, BASE_DIR
from MrMap.views import GenericViewContextMixin, InitFormMixin, CustomSingleTableMixin, \
    SuccessMessageDeleteMixin
from service.filters import OgcWmsFilter, DatasetFilter, ProxyLogTableFilter, PendingTaskFilter
from service.forms import UpdateServiceCheckForm, UpdateOldToNewElementsForm, MapContextForm
from service.helper import service_helper
from service.helper import update_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCOperationEnum, OGCServiceVersionEnum, MetadataEnum
from service.serializer.ogc.operation_request_handler import OGCOperationRequestHandler
from service.helper.service_comparator import ServiceComparator
from service.helper.service_helper import get_resource_capabilities
from service.models import Metadata, Layer, Service, Style, ProxyLog, MapContext
from service.settings import DEFAULT_SRS_STRING, PREVIEW_MIME_TYPE_DEFAULT, PLACEHOLDER_IMG_PATH
from service.tables import UpdateServiceElements, DatasetTable, OgcServiceTable, PendingTaskTable, ResourceDetailTable, \
    ProxyLogTable, MapContextTable
from service.tasks import async_log_response
from service.utils import collect_contact_data, collect_metadata_related_objects, collect_featuretype_data, \
    collect_layer_data, collect_wms_root_data, collect_wfs_root_data
from structure.models import PendingTask
from structure.permissionEnums import PermissionEnum
from django.urls import reverse, reverse_lazy
from users.models import Subscription
from django.db.models import Prefetch


def test(request):
    import os

    from eulxml import xmlmap
    from service.serializer.ogc.parser.new import Service as PlainService
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(BASE_DIR)
    xml_obj = xmlmap.load_xmlobject_from_file(filename=current_dir + '/dwd_wms_1.3.0.xml', xmlclass=PlainService)
    xml_obj.to_db()
    return HttpResponse(status=200)

def get_queryset_filter_by_service_type(service_type: OGCServiceEnum) -> QuerySet:
    qs = Metadata.objects.filter(
        service__service_type__name=service_type.value,
        is_deleted=False,
        service__is_update_candidate_for=None,
    ).select_related(
        "contact",
        "owned_by_org",
        "service",
        "service__service_type",
        "service__parent_service__metadata",
        "external_authentication",
    ).prefetch_related(
        Prefetch("health_states", queryset=HealthState.objects.only('health_state_code', 'reliability_1w')),
    ).order_by(
        "title",
    ).only(
        "title",
        "is_active",
        "use_proxy_uri",
        "log_proxy_access",
        "is_secured",
        "metadata_type",
        "created_at",
        "contact__name",
        "owned_by_org__name",
        "service__is_active",
        "service__service_type__version",
        "service__service_type__name",
        "service__parent_service__metadata__title",
        "service__parent_service__metadata__is_active",
        "external_authentication__id",
    )
    if service_type == OGCServiceEnum.WMS:
        qs.prefetch_related(
            "service__child_services",
        )
    elif service_type == OGCServiceEnum.WFS:
        qs.prefetch_related(
            "service__featuretypes",
        )
    elif service_type == OGCServiceEnum.CSW:
        qs.prefetch_related(
            Prefetch("harvest_results", queryset=HarvestResult.objects.only('timestamp_end', 'timestamp_start', 'number_results')),
        )

    return qs


class PendingTaskView(SecuredListMixin, FilterView):
    model = PendingTask
    table_class = PendingTaskTable
    filterset_class = PendingTaskFilter
    title = get_icon(IconEnum.PENDING_TASKS) + _(' Pending tasks').__str__()
    template_name = 'service/views/pending_tasks.html'


class WmsIndexView(SecuredListMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_class = OgcWmsFilter
    queryset = get_queryset_filter_by_service_type(service_type=OGCServiceEnum.WMS)
    title = get_icon(IconEnum.WMS) + _(' WMS').__str__()

    def get_filterset_kwargs(self, *args):
        kwargs = super(WmsIndexView, self).get_filterset_kwargs(*args)
        if kwargs['data'] is None:
            kwargs['queryset'] = kwargs['queryset'].filter(service__is_root=True)
        return kwargs

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(WmsIndexView, self).get_table(**kwargs)
        # whether whole services or single layers should be displayed, we have to exclude some columns
        filter_by_show_layers = self.filterset.form_prefix + '-' + 'service__is_root'
        if filter_by_show_layers in self.filterset.data and self.filterset.data.get(filter_by_show_layers) == 'on':
            table.exclude = (
                'layers', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)
        else:
            table.exclude = (
                'parent_service', 'featuretypes', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table


class WfsIndexView(SecuredListMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_fields = {'title': ['icontains'], }
    queryset = get_queryset_filter_by_service_type(service_type=OGCServiceEnum.WFS)
    title = get_icon(IconEnum.WFS) + _(' WFS').__str__()

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(WfsIndexView, self).get_table(**kwargs)
        table.exclude = ('parent_service', 'layers', 'last_harvested', 'collected_harvest_records', 'last_harvest_duration',)

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table


class CswIndexView(SecuredListMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_fields = {'title': ['icontains'], }
    queryset = get_queryset_filter_by_service_type(service_type=OGCServiceEnum.CSW)
    title = get_icon(IconEnum.CSW) + _(' CSW').__str__()

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(CswIndexView, self).get_table(**kwargs)
        table.exclude = ('parent_service', 'layers', 'featuretypes', 'service__published_for')
        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table


class DatasetIndexView(SecuredListMixin, FilterView):
    model = Metadata
    table_class = DatasetTable
    filterset_class = DatasetFilter
    title = get_icon(IconEnum.DATASET) + _(' Dataset').__str__()

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(DatasetIndexView, self).get_table(**kwargs)
        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_dataset_action())]
        return table

    def get_queryset(self):
        return self.request.user.get_instances(klass=Metadata, filter=Q(metadata_type=MetadataEnum.DATASET.value))


class ResourceDeleteView(SecuredDeleteView):
    model = Metadata
    queryset = Metadata.objects.filter(Q(metadata_type=MetadataEnum.SERVICE.value) |
                                       Q(metadata_type=MetadataEnum.CATALOGUE.value))
    success_url = reverse_lazy('home')
    template_name = "MrMap/detail_views/delete.html"
    success_message = SERVICE_SUCCESSFULLY_DELETED

    def get_msg_dict(self):
        return {'name': self.get_object()}


class ResourceActivateDeactivateView(SecuredUpdateView):
    model = Metadata
    fields = ('is_active',)
    permission_required = PermissionEnum.CAN_ACTIVATE_RESOURCE.value

    def get_title(self):
        if self.object.is_active:
            return _('Deactivate service')
        else:
            return _('Activate service')

    def get_success_message(self, cleaned_data):
        if cleaned_data['is_active']:
            self.success_message = SERVICE_ACTIVATED
        else:
            self.success_message = SERVICE_DEACTIVATED
        cleaned_data.update({'title': self.object.title})
        return super().get_success_message(cleaned_data)


def get_service_metadata(request: HttpRequest, metadata_id):
    """ Returns the service metadata xml file for a given metadata id

    Args:
        metadata_id: The metadata id
    Returns:
         A HttpResponse containing the xml file
    """

    metadata = get_object_or_404(Metadata, id=metadata_id)

    if not metadata.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    doc = metadata.get_service_metadata_xml()

    return HttpResponse(doc, content_type=APP_XML)


@login_required
def metadata_subscription_new(request: HttpRequest, metadata_id: str):
    """ Creates a new subscription for a metadat without a form

    Args:
        request (HttpRequest): The incoming request
        metadata_id (str): The id of the metadata which shall be subscribed
    Returns:
         A rendered view
    """
    md = get_object_or_404(Metadata, id=metadata_id)
    user = request.user
    subscription_created = Subscription.objects.get_or_create(
        metadata=md,
        user=user,
    )[1]
    if subscription_created:
        messages.success(request, SUBSCRIPTION_SUCCESSFULLY_CREATED.format(md.title))
    else:
        messages.info(request, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE.format(md.title))

    return redirect("subscription-index")


class DatasetMetadataXmlView(BaseDetailView):
    model = Metadata
    # a dataset metadata without a document is broken
    queryset = Metadata.objects.filter(metadata_type=OGCServiceEnum.DATASET.value, documents__isnull=False) \
        .prefetch_related('documents')
    content_type = 'application/xml'
    object = None

    def get(self, request, *args, **kwargs):
        document = self.object.documents.get(is_original=False) if self.object.documents.filter(
            is_original=False).exists() else self.object.documents.get(
            is_original=True)
        return HttpResponse(document.content, content_type=self.content_type)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_active:
            return HttpResponse(content=SERVICE_DISABLED, status=423)
        else:
            return super().dispatch(request, *args, **kwargs)


def get_service_preview(request: HttpRequest, metadata_id):
    """ Returns the service metadata preview as png for a given metadata id

    Args:
        request (HttpRequest): The incoming request
        metadata_id: The metadata id
    Returns:
         A HttpResponse containing the png preview
    """

    md = get_object_or_404(Metadata, id=metadata_id)
    if md.is_metadata_type(MetadataEnum.DATASET) or \
            md.is_metadata_type(MetadataEnum.FEATURETYPE) or \
            not md.service.is_service_type(OGCServiceEnum.WMS) or md.is_updatecandidate:
        return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

    if md.service.is_service_type(OGCServiceEnum.WMS) and md.service.is_root:
        service = get_object_or_404(Service, id=md.service.id)
        layer = get_object_or_404(Layer, parent_service=service, parent=None, )
        # Fake the preview image for the whole service by using the root layer instead
        md = layer.metadata
    elif md.service.is_service_type(OGCServiceEnum.WMS) and not md.service.is_root:
        layer = md.service.layer

    layer = layer.identifier
    if md.allowed_area.area == 0:
        bbox = md.find_max_bounding_box()
    else:
        bbox = md.allowed_area
    bbox = str(bbox.extent).replace("(", "").replace(")", "")  # this is a little dumb, you may choose something better

    img_width = 200
    img_heigt = 200

    try:
        # Fetch a pixel based image mime type. We can not use vector types
        png_format = md.get_formats().filter(
            mime_type__icontains="image/"
        ).exclude(
            mime_type__icontains="svg"
        ).first()
        img_format = png_format.mime_type
    except AttributeError:
        # Act as fallback
        img_format = "image/png"

    data = {
        "request": OGCOperationEnum.GET_MAP.value,
        "version": OGCServiceVersionEnum.V_1_1_1.value,
        "layers": layer,
        "srs": DEFAULT_SRS_STRING,
        "bbox": bbox,
        "format": img_format,
        "width": img_width,
        "height": img_heigt,
        "service": "wms",
    }

    query_data = QueryDict('', mutable=True)
    query_data.update(data)

    request.POST._mutable = True
    request.POST = query_data
    request.method = 'POST'
    request.POST._mutable = False

    # Check if this parameters already have been generated a preview image for this metadata record
    cacher = PreviewImageCacher(metadata=md)
    img = cacher.get(data)

    if img is None:
        # There is no cached image, so we create one and cache it!
        operation_request_handler = OGCOperationRequestHandler(request=request, metadata=md)
        img = operation_request_handler.get_operation_response(post_data=data)  # img is returned as a byte code
        cacher.set(data, img)

    response = img.get("response", None)
    content_type = img.get("response_type", "")

    try:
        # Make sure the image is returned as PREVIEW_MIME_TYPE_DEFAULT filetype
        image_obj = Image.open(io.BytesIO(response))
    except UnidentifiedImageError:
        # No preview image could be generated. We need to open a placeholder image!
        image_obj = Image.open(PLACEHOLDER_IMG_PATH)
        image_obj = image_obj.resize((img_width, img_heigt))

    out_bytes_stream = io.BytesIO()
    image_obj.save(out_bytes_stream, PREVIEW_MIME_TYPE_DEFAULT, optimize=True, quality=80)
    response = out_bytes_stream.getvalue()

    return HttpResponse(response, content_type=content_type)


def _get_capabilities(request: HttpRequest, metadata_id):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        metadata_id : The metadata id
    Returns:
         A HttpResponse containing the xml file
    """

    md = get_object_or_404(Metadata, id=metadata_id)
    try:
        doc = get_resource_capabilities(request, md)
    except (ReadTimeout, TimeoutError, ConnectionError) as e:
        # the remote server does not respond - we must deliver our stored capabilities document, which is not the requested version
        return HttpResponse(content=SERVICE_CAPABILITIES_UNAVAILABLE)
    return HttpResponse(doc, content_type='application/xml')


class MetadataHtml(DetailView):
    model = Metadata
    queryset = Metadata.objects.select_related('service').filter(service__is_update_candidate_for=None)
    extra_context = {"SEMANTIC_WEB_HTML_INFORMATION": SEMANTIC_WEB_HTML_INFORMATION}

    def get_template_names(self):
        if self.object.is_metadata_type(MetadataEnum.DATASET):
            self.template_name = 'metadata/base/dataset/dataset_metadata_as_html.html'
        elif self.object.is_metadata_type(MetadataEnum.FEATURETYPE):
            self.template_name = 'metadata/base/wfs/featuretype_metadata_as_html.html'
        elif self.object.is_metadata_type(MetadataEnum.LAYER):
            self.template_name = 'metadata/base/wms/layer_metadata_as_html.html'
        elif self.object.service.is_service_type(OGCServiceEnum.WMS):
            # wms root object
            self.template_name = 'metadata/base/wms/root_metadata_as_html.html'
        elif self.object.service.is_service_type(OGCServiceEnum.WFS):
            # wfs root object
            self.template_name = 'metadata/base/wfs/root_metadata_as_html.html'
        elif self.object.is_catalogue_metadata:
            # ToDo: Add html view for CSW!
            pass
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # todo: refactor this messy context by using just the self.object from default context....
        context.update({
            'md_id': self.object.id,
            'title': self.object.title,
            'abstract': self.object.abstract,
            'access_constraints': self.object.access_constraints,
            'capabilities_original_uri': self.object.capabilities_original_uri,
            'capabilities_uri': self.object.capabilities_uri,
            'contact': collect_contact_data(self.object.contact),
            "SEMANTIC_WEB_HTML_INFORMATION": SEMANTIC_WEB_HTML_INFORMATION,
        })

        context.update(collect_metadata_related_objects(self.object, self.request, ))

        if self.object.is_metadata_type(MetadataEnum.DATASET):
            context['contact'] = collect_contact_data(self.object.contact)
            context['bounding_box'] = self.object.bounding_geometry
            context['dataset_metadata'] = self.object
            context['fees'] = self.object.fees
            context['licence'] = self.object.licence
            context.update({'capabilities_uri': self.object.service_metadata_uri})

        elif self.object.is_metadata_type(MetadataEnum.FEATURETYPE):
            context.update(collect_featuretype_data(self.object))

        elif self.object.is_metadata_type(MetadataEnum.LAYER):
            context.update(collect_layer_data(self.object, self.request))

        elif self.object.service.is_service_type(OGCServiceEnum.WMS):
            # wms root object
            context.update(collect_wms_root_data(self.object, self.request))

        elif self.object.service.is_service_type(OGCServiceEnum.WFS):
            # wfs root object
            context.update(collect_wfs_root_data(self.object, self.request))

        elif self.object.is_catalogue_metadata:
            # ToDo: Add html view for CSW!
            pass

        return context


@login_required
# @permission_required(PermissionEnum.CAN_UPDATE_RESOURCE.value)
# @ownership_required(Metadata, 'metadata_id')
@transaction.atomic
def new_pending_update_service(request: HttpRequest, metadata_id):
    """ Compare old service with new service and collect differences

    Args:
        request: The incoming request
        metadata_id: The service id
    Returns:
        A rendered view
    """
    current_service = get_object_or_404(Service, metadata__id=metadata_id)
    user = request.user

    form = UpdateServiceCheckForm(data=request.POST or None,
                                  request=request,
                                  reverse_lookup='resource:new-pending-update',
                                  reverse_args=[metadata_id, ],
                                  # ToDo: after refactoring of all forms is done, show_modal can be removed
                                  show_modal=True,
                                  current_service=current_service,
                                  requesting_user=user,
                                  form_title=_l(
                                      f'Update service: <strong>{current_service.metadata.title} [{current_service.metadata.id}]</strong>'))
    if request.method == 'GET':
        return form.render_view()

    if request.method == 'POST':
        # Check if update form is valid
        if form.is_valid():
            # Create db model from new service information (no persisting, yet)
            new_service = service_helper.create_service(
                service_type=form.url_dict.get("service"),
                version=service_helper.resolve_version_enum(form.url_dict.get("version")),
                base_uri=form.url_dict.get("base_uri"),
                user=user,
                register_group=current_service.created_by,
                is_update_candidate_for=current_service,
            )
            new_service.created_by_user = user
            new_service.keep_custom_md = form.cleaned_data['keep_custom_md']
            new_service.metadata.is_update_candidate_for = current_service.metadata
            new_service.metadata.created_by_user = user
            new_service.save()
            return HttpResponseRedirect(reverse("resource:pending-update", args=(metadata_id,)), status=303)
        else:
            form.fade_modal = False
            return form.render_view(status_code=422)

    return HttpResponseRedirect(reverse(request.GET.get('current-view', None), args=(metadata_id,)), status=303)


# Todo: wizard/form view?
@login_required
@permission_required(PermissionEnum.CAN_UPDATE_RESOURCE.value)
@transaction.atomic
def pending_update_service(request: HttpRequest, metadata_id, update_params: dict = None, status_code: int = 200, ):
    template = "views/service_update.html"

    current_service = get_object_or_404(Service, metadata__id=metadata_id)
    try:
        new_service = Service.objects.get(is_update_candidate_for=current_service)
    except ObjectDoesNotExist:
        messages.error(request, _l("No updatecandidate was found."))
        # ToDo: make 7 dynamic
        messages.info(request, _l("Update candidates will be deleted after 7 days."))
        return HttpResponseRedirect(reverse("resource:detail", args=(metadata_id,)), status=303)

    if current_service.is_service_type(OGCServiceEnum.WMS):
        current_service.root_layer = Layer.objects.get(parent_service=current_service, parent=None)
        new_service.root_layer = Layer.objects.get(parent_service=new_service, parent=None)

    # Collect differences
    comparator = ServiceComparator(service_a=new_service, service_b=current_service)
    diff = comparator.compare_services()

    diff_elements = diff.get("layers", None) or diff.get("feature_types", {})
    update_confirmation_form = UpdateOldToNewElementsForm(
        new_elements=diff_elements.get("new"),
        removed_elements=diff_elements.get("removed"),
        current_service=current_service,
    )
    update_confirmation_form.action_url = reverse("resource:run-update", args=[metadata_id])

    updated_elements_md = []
    for element in diff_elements.get("updated"):
        updated_elements_md.append(element.metadata)

    removed_elements_md = []
    for element in diff_elements.get("removed"):
        removed_elements_md.append(element.metadata)

    updated_elements_table = UpdateServiceElements(request=request,
                                                   queryset=updated_elements_md,
                                                   current_view="resource:dismiss-pending-update",
                                                   order_by_field='updated', )

    removed_elements_table = UpdateServiceElements(request=request,
                                                   queryset=removed_elements_md,
                                                   current_view="resource:dismiss-pending-update",
                                                   order_by_field='removed',
                                                   )

    params = {
        "current_service": current_service,
        "update_service": new_service,
        "diff_elements": diff_elements,
        "updated_elements_table": updated_elements_table,
        "removed_elements_table": removed_elements_table,
        "update_confirmation_form": update_confirmation_form,
        "new_elements_per_page": request.GET.get('new_elements_per_page', 5),
    }

    if update_params:
        params.update(update_params)

    return render(request=request,
                  template_name=template,
                  context=params,
                  status=status_code)


@login_required
@permission_required(PermissionEnum.CAN_UPDATE_RESOURCE.value)
@transaction.atomic
def dismiss_pending_update_service(request: HttpRequest, metadata_id):
    user = request.user
    current_service = get_object_or_404(Service, metadata__id=metadata_id)
    new_service = get_object_or_404(Service, is_update_candidate_for=current_service)

    if request.method == 'POST':
        if new_service.created_by_user == user:
            new_service.delete()
            messages.success(request, _l("Pending update successfully dismissed."))
        else:
            messages.error(request, _l("You are not the owner of this pending update. Rejected!"))

        return HttpResponseRedirect(reverse("resource:detail", args=(current_service.metadata.id,)), status=303)

    return HttpResponseRedirect(reverse("resource:pending-update", args=(current_service.metadata.id,)), status=303)


@login_required
@permission_required(PermissionEnum.CAN_UPDATE_RESOURCE.value)
@transaction.atomic
def run_update_service(request: HttpRequest, metadata_id):
    if request.method == 'POST':
        current_service = get_object_or_404(
            Service.objects.select_related('metadata').prefetch_related('metadata__documents'),
            metadata__id=metadata_id)
        new_service = get_object_or_404(
            Service.objects.select_related('metadata').prefetch_related('metadata__documents'),
            is_update_candidate_for=current_service)

        if not current_service.is_service_type(OGCServiceEnum.WFS):
            new_service.root_layer = get_object_or_404(Layer, parent_service=new_service, parent=None)
            current_service.root_layer = get_object_or_404(Layer, parent_service=current_service, parent=None)

        comparator = ServiceComparator(service_a=new_service, service_b=current_service)
        diff = comparator.compare_services()

        diff_elements = diff.get("layers", None) or diff.get("feature_types", {})

        # We need to extract the linkage of new->old elements from the request by hand
        # key identifies the new element and it's identifier (not id!) and choice identifies the existing element's id!
        links = {}
        prefix = "new_elem_"
        for key, choice in request.POST.items():
            if prefix in key:
                links[key.replace(prefix, "")] = choice

        update_confirmation_form = UpdateOldToNewElementsForm(request.POST,
                                                              new_elements=diff_elements.get("new"),
                                                              removed_elements=diff_elements.get("removed"),
                                                              choices=links,
                                                              current_service=current_service,
                                                              )
        update_confirmation_form.action_url = reverse("resource:run-update", args=[metadata_id])
        if update_confirmation_form.is_valid():
            # UPDATE
            # First update the metadata of the whole service
            md = update_helper.update_metadata(
                current_service.metadata,
                new_service.metadata,
                new_service.keep_custom_md
            )
            md.save()
            current_service.metadata = md
            current_service.save()

            # Then update the service object
            current_service = update_helper.update_service(current_service, new_service)
            current_service.save()

            # Update the subelements
            if new_service.is_service_type(OGCServiceEnum.WFS):
                current_service = update_helper.update_wfs_elements(
                    current_service,
                    new_service,
                    diff,
                    links,
                    new_service.keep_custom_md
                )
            elif new_service.is_service_type(OGCServiceEnum.WMS):
                # takes long time | todo proof again after using django-mptt
                current_service = update_helper.update_wms_elements(
                    current_service,
                    new_service,
                    diff,
                    links,
                    new_service.keep_custom_md
                )

            current_service.save()

            update_helper.update_capability_document(current_service, new_service)

            current_service.save()

            new_service.delete()

            messages.success(request, SERVICE_UPDATED)
            return HttpResponseRedirect(reverse("resource:detail", args=(metadata_id,)), status=303)
        else:
            params = {"update_confirmation_form": update_confirmation_form, }
            return pending_update_service(request=request,
                                          metadata_id=metadata_id,
                                          update_params=params,
                                          status_code=422)
    else:
        return HttpResponseRedirect(reverse("resource:pending-update", args=(metadata_id,)), status=303)


class ResourceDetailTableView(SecuredDetailView):
    model = Metadata
    template_name = 'generic_views/generic_detail_without_base.html'
    queryset = Metadata.objects.all().prefetch_related('contact', 'service', 'service__layer', 'featuretype')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details = ResourceDetailTable(data=[self.object, ], request=self.request, )
        details = render_to_string(template_name='skeletons/django_tables2_render_table.html',
                                   context={'table': details})
        context.update({'card_body': details})
        return context


class ResourceRelatedDatasetView(SecuredDetailView):
    model = Metadata
    template_name = 'generic_views/generic_detail_without_base.html'
    queryset = Metadata.objects.all().prefetch_related('related_metadatas', )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        related_datasets = self.object.get_related_dataset_metadatas()

        item_list = []
        for related_dataset in related_datasets:
            link_to_dataset = Link(url=related_dataset.detail_view_uri, content=related_dataset.title)

            metadata_xml = Link(url=related_dataset.service_metadata_uri,
                                content=get_icon(IconEnum.CAPABILITIES) + _(' XML'),
                                open_in_new_tab=True)
            metadata_html = Link(url=related_dataset.html_metadata_uri,
                                 content=get_icon(IconEnum.NEWSPAPER) + _(' HTML'),
                                 open_in_new_tab=True)

            dataset_metadata_dropdown = Dropdown(btn_value=get_icon(IconEnum.METADATA) + _(' Metadata'),
                                                 items=[metadata_xml, metadata_html],
                                                 color=ButtonColorEnum.SECONDARY,
                                                 header=_l('Show metadata as:'))

            render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                         update_url_qs=get_current_view_args(request=self.request),
                                         update_attrs={"class": ["btn-sm", "mr-1"]})
            right = render_helper.render_list_coherent(items=related_dataset.get_actions())

            item_content = DefaultHeaderRow(content_left=link_to_dataset.render(),
                                            content_center=dataset_metadata_dropdown.render(),
                                            content_right=right)
            item_list.append(ListGroupItem(content=item_content.render()))

        dataset_list = ListGroup(items=item_list)

        context.update({'card_body': dataset_list if related_datasets else ''})
        return context


def render_actions(element, render_helper):
    element.actions = render_helper.render_list_coherent(safe=True, items=element.metadata.get_actions())
    return element.actions


class ResourceTreeView(SecuredDetailView):
    model = Metadata
    template_name = 'generic_views/resource.html'
    available_resources = Q(metadata_type='layer') | \
                          Q(metadata_type='featureType') | \
                          Q(service__service_type__name='wms') | \
                          Q(service__service_type__name='wfs') | \
                          Q(service__service_type__name='csw') & \
                          Q(service__is_update_candidate_for=None)
    queryset = Metadata.objects. \
        select_related('service', 'service__service_type', 'featuretype', 'owned_by_org'). \
        prefetch_related('service__featuretypes', 'service__child_services', 'featuretype__elements'). \
        filter(available_resources)
    render_helper = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                          update_attrs={"class": ["btn-sm", "mr-1"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'tree_style': True})

        if self.object.is_featuretype_metadata:
            self.template_name = 'service/views/featuretype.html'
        elif self.object.is_service_type(enum=OGCServiceEnum.WFS):
            self.template_name = 'service/views/wfs_tree.html'
            sub_elements = self.object.get_described_element().get_subelements().select_related(
                'metadata').prefetch_related('elements')
            context.update({'featuretypes': sub_elements})
        elif self.object.is_layer_metadata or self.object.is_service_type(enum=OGCServiceEnum.WMS):
            sub_elements = self.object.get_described_element().get_subelements().select_related('metadata')
            self.template_name = 'service/views/wms_tree.html'
            context.update({'nodes': sub_elements,
                            'root_node': self.object.service})
        elif self.object.is_service_type(enum=OGCServiceEnum.CSW):
            self.template_name = 'service/views/csw.html'
            pass
        return context


@csrf_exempt
@log_proxy
def get_operation_result(request: HttpRequest, proxy_log: ProxyLog, metadata_id):
    """ Checks whether the requested metadata is secured and resolves the operations uri for an allowed user - or not.

    Decides which operation will be handled by resolving a given 'request=' query parameter.
    This function has to be public available (no check_session decorator)
    The decorator allows POST requests without CSRF tokens (for non logged in users)

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        metadata_id: The metadata id
    Returns:
         A redirect to the GetMap uri
    """
    # get request type and requested layer
    get_query_string = request.META.get("QUERY_STRING", "")

    try:
        # redirects request to parent service, if the given id is not the root of the service
        metadata = Metadata.objects.get(id=metadata_id)
        operation_handler = OGCOperationRequestHandler(uri=get_query_string, request=request, metadata=metadata)

        if not metadata.is_active:
            return HttpResponse(status=423, content=SERVICE_DISABLED)

        elif operation_handler.request_param is None:
            return HttpResponse(status=500, content=SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE)

        elif operation_handler.request_param.upper() == OGCOperationEnum.GET_CAPABILITIES.value.upper():
            return _get_capabilities(request=request, metadata_id=metadata_id)

        elif not metadata.is_root():
            # we do not allow the direct call of operations on child elements, such as layers!
            # if the request tries that, we directly redirect it to the parent service!
            parent_md = metadata.service.parent_service.metadata
            return get_operation_result(request=request, id=parent_md.id)

        # We need to check if at least one of the requested layers is secured.
        md_secured = metadata.is_secured
        if operation_handler.layers_param is not None:
            layers = operation_handler.layers_param.split(",")
            layers_md = Metadata.objects.filter(
                identifier__in=layers,
                service__parent_service__metadata=metadata
            )
            md_secured = layers_md.filter(is_secured=True).exists()

            if layers_md.count() != len(layers):
                # at least one requested layer could not be found in the database
                return HttpResponse(status=404, content=SERVICE_LAYER_NOT_FOUND)
        if md_secured:
            response_dict = operation_handler.get_allowed_operation_response()
        else:
            response_dict = operation_handler.get_operation_response(proxy_log=proxy_log)

        response = response_dict.get("response", None)
        content_type = response_dict.get("response_type", "")

        if response is None:
            # metadata is secured but user is not allowed
            return HttpResponse(status=401, content=SECURITY_PROXY_NOT_ALLOWED)

        # Log the response, if needed
        if proxy_log is not None:
            response_encoded = base64.b64encode(response).decode("UTF-8")
            async_log_response.delay(
                proxy_log.id,
                response_encoded,
                operation_handler.request_param,
                operation_handler.format_param,
            )

        len_response = len(response)
        if len_response <= 5000000:
            return HttpResponse(response, content_type=content_type)
        else:
            # data too big - we should stream it!
            # make sure the response is in bytes
            if not isinstance(response, bytes):
                response = bytes(response)
            buffer = BytesIO(response)
            return StreamingHttpResponse(buffer, content_type=content_type)

    except ObjectDoesNotExist:
        return HttpResponse(status=404, content=SERVICE_NOT_FOUND)
    except ReadTimeout:
        return HttpResponse(status=408, content=CONNECTION_TIMEOUT.format(request.build_absolute_uri()))
    #except Exception as e:
    #    return HttpResponse(status=500, content=e)


def get_metadata_legend(request: HttpRequest, metadata_id, style_id: int):
    """ Calls the legend uri of a special style inside the metadata (<LegendURL> element) and returns the response to the user

    This function has to be public available (no check_session decorator)

    Args:
        request (HttpRequest): The incoming HttpRequest
        metadata_id: The metadata id
        style_id (int): The style id
    Returns:
        HttpResponse
    """
    style = get_object_or_404(Style, id=style_id)
    uri = style.legend_uri
    con = CommonConnector(uri)
    con.load()
    response = con.content
    return HttpResponse(response, content_type="")


class LogsIndexView(SecuredListMixin, ExportMixin, FilterView):
    model = ProxyLog
    table_class = ProxyLogTable
    filterset_class = ProxyLogTableFilter
    export_name = f'MrMap_logs_{timezone.now().strftime("%Y-%m-%dT%H_%M_%S")}'

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(LogsIndexView, self).get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.LOGS.value]}) + _(' Logs')

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))

        # append export links
        query_trailer_sign = "?"
        if self.request.GET:
            query_trailer_sign = "&"
        csv_download_link = Link(url=self.request.get_full_path() + f"{query_trailer_sign}_export=csv", content=".csv")
        json_download_link = Link(url=self.request.get_full_path() + f"{query_trailer_sign}_export=json",
                                  content=".json")

        dropdown = Dropdown(btn_value=Tag(tag='i', attrs={"class": [IconEnum.DOWNLOAD.value]}) + _(" Export as"),
                            items=[csv_download_link, json_download_link],
                            needs_perm=PermissionEnum.CAN_VIEW_PROXY_LOG.value)
        table.actions = [render_helper.render_item(item=dropdown)]
        return table


# TODO
@method_decorator(login_required, name='dispatch')
class MapContextIndexView(CustomSingleTableMixin, FilterView):
    model = MapContext
    table_class = MapContextTable
    filterset_fields = {'title': ['icontains'], }
    title = get_icon(IconEnum.MAP_CONTEXT) + _(' Map Contexts').__str__()

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(MapContextIndexView, self).get_table(**kwargs)
        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_all_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=MapContext.get_add_action())]
        return table

    def get_queryset(self):
        return MapContext.objects.all()


@method_decorator(login_required, name='dispatch')
class MapContextCreateView(SecuredCreateView):
    model = MapContext
    form_class = MapContextForm
    template_name = 'views/map_context_add.html'
    success_message = MAP_CONTEXT_SUCCESSFULLY_CREATED
    success_url = reverse_lazy('resource:mapcontexts-index')


@method_decorator(login_required, name='dispatch')
class MapContextEditView(SecuredUpdateView):
    template_name = 'views/map_context_add.html'
    success_message = MAP_CONTEXT_SUCCESSFULLY_EDITED
    success_url = reverse_lazy('resource:mapcontexts-index')
    model = MapContext
    form_class = MapContextForm


@method_decorator(login_required, name='dispatch')
class MapContextDeleteView(SecuredDeleteView):
    model = MapContext
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('resource:mapcontexts-index')
    success_message = MAP_CONTEXT_SUCCESSFULLY_DELETED

    def get_msg_dict(self):
        return {'name': self.get_object().title}
