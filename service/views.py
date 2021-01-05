import base64
import io
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, QueryDict, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, TemplateView, DetailView
from django_bootstrap_swt.components import Tag, Link, Dropdown, ListGroupItem, ListGroup, DefaultHeaderRow, Modal, \
    Badge, Accordion, Card, CardHeader
from django_bootstrap_swt.enums import ButtonColorEnum, ModalSizeEnum
from django_bootstrap_swt.utils import RenderHelper
from django_filters.views import FilterView
from django_tables2 import SingleTableMixin
from requests.exceptions import ReadTimeout
from django.utils import timezone
from MrMap.cacher import PreviewImageCacher
from MrMap.consts import *
from MrMap.decorator import check_permission, log_proxy, check_ownership, resolve_metadata_public_id
from MrMap.forms import get_current_view_args
from MrMap.icons import IconEnum
from MrMap.messages import SERVICE_UPDATED, \
    SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED, SERVICE_LAYER_NOT_FOUND, \
    SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT, SERVICE_CAPABILITIES_UNAVAILABLE, \
    SUBSCRIPTION_CREATED_TEMPLATE, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE
from MrMap.responses import DefaultContext
from MrMap.settings import SEMANTIC_WEB_HTML_INFORMATION
from MrMap.themes import FONT_AWESOME_ICONS
from service.filters import OgcWmsFilter, OgcWfsFilter, OgcCswFilter, DatasetFilter
from service.forms import UpdateServiceCheckForm, UpdateOldToNewElementsForm, RemoveServiceForm, \
    ActivateServiceForm
from service.helper import service_helper, update_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCOperationEnum, OGCServiceVersionEnum, MetadataEnum, DocumentEnum
from service.helper.logger_helper import prepare_proxy_log_filter
from service.helper.ogc.operation_request_handler import OGCOperationRequestHandler
from service.helper.service_comparator import ServiceComparator
from service.helper.service_helper import get_resource_capabilities
from service.settings import DEFAULT_SRS_STRING, PREVIEW_MIME_TYPE_DEFAULT, PLACEHOLDER_IMG_PATH
from service.tables import UpdateServiceElements, DatasetTable, OgcServiceTable, PendingTaskTable, ResourceDetailTable, \
    FeatureTypeElementTable
from service.tasks import async_log_response
from service.models import Metadata, Layer, Service, Document, Style, ProxyLog, FeatureTypeElement
from service.utils import collect_contact_data, collect_metadata_related_objects, collect_featuretype_data, \
    collect_layer_data, collect_wms_root_data, collect_wfs_root_data
from service.wizards import NEW_RESOURCE_WIZARD_FORMS, NewResourceWizard
from structure.models import PendingTask
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper
from django.urls import reverse

from users.models import Subscription


def default_dispatch(instance, extra_context=None, with_base: bool = True, is_list_view: bool = True):
    if is_list_view:
        # configure table_pagination dynamically to support per_page switching
        instance.table_pagination = {"per_page": instance.request.GET.get('per_page', 5), }

    if extra_context is None:
        extra_context = {}
    # push DefaultContext to the template rendering engine
    instance.extra_context = DefaultContext(request=instance.request, context=extra_context).get_context()

    with_base = instance.request.GET.get('with-base', 'True' if with_base else 'False')
    if with_base == 'True':
        instance.template_name = 'generic_views/generic_list_with_base.html' if is_list_view else 'generic_views/generic_detail_with_base.html'
    else:
        instance.template_name = 'generic_views/generic_list_without_base.html' if is_list_view else 'generic_views/generic_detail_without_base.html'


def get_queryset_filter_by_service_type(instance, service_type: OGCServiceEnum):
    return Metadata.objects.filter(
        service__service_type__name=service_type.value,
        created_by__in=instance.request.user.get_groups(),
        is_deleted=False,
        service__is_update_candidate_for=None,
    ).prefetch_related(
        "contact",
        "service",
        "service__created_by",
        "service__published_for",
        "service__service_type",
        "external_authentication",
        "service__parent_service__metadata",
        "service__parent_service__metadata__external_authentication",
    ).order_by("title")


class PendingTaskView(SingleTableMixin, ListView):
    model = PendingTask
    table_class = PendingTaskTable

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(PendingTaskView, self).get_table(**kwargs)
        if table.data.data:
            table.title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Pending tasks')
        else:
            self.template_name = 'generic_views/empty.html'
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self, with_base=False)
        return super(PendingTaskView, self).dispatch(request, *args, **kwargs)


class WmsIndexView(SingleTableMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_class = OgcWmsFilter

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
            table.exclude = ('layers', 'featuretypes', 'last_harvest', 'collected_harvest_records', )
        else:
            table.exclude = ('parent_service', 'featuretypes', 'last_harvest', 'collected_harvest_records',)

        table.title = Tag(tag='i', attrs={"class": [IconEnum.WMS.value]}) + _(' WMS')

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        # we inject the pending task ajax template above the default content to support polling the dynamic content
        extra_context = {'above_content': render_to_string(template_name='pending_task_list_ajax.html')}
        extra_context.update(kwargs.get('update_params', {}))
        default_dispatch(instance=self, extra_context=extra_context)
        return super(WmsIndexView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return get_queryset_filter_by_service_type(instance=self, service_type=OGCServiceEnum.WMS)


class WfsIndexView(SingleTableMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_class = OgcWfsFilter

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(WfsIndexView, self).get_table(**kwargs)
        table.exclude = ('parent_service', 'layers', 'last_harvest', 'collected_harvest_records',)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.WFS.value]}) + _(' WFS')

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        # we inject the pending task ajax template above the default content to support polling the dynamic content
        extra_context = {'above_content': render_to_string(template_name='pending_task_list_ajax.html')}
        extra_context.update(kwargs.get('update_params', {}))
        default_dispatch(instance=self, extra_context=extra_context)
        return super(WfsIndexView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return get_queryset_filter_by_service_type(instance=self, service_type=OGCServiceEnum.WFS)


class CswIndexView(SingleTableMixin, FilterView):
    model = Metadata
    table_class = OgcServiceTable
    filterset_class = OgcCswFilter

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(CswIndexView, self).get_table(**kwargs)
        table.exclude = ('parent_service', 'layers', 'featuretypes', 'health', 'service__published_for')
        table.title = Tag(tag='i', attrs={"class": [IconEnum.CSW.value]}) + _(' CSW')

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_resource_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        # we inject the pending task ajax template above the default content to support polling the dynamic content
        extra_context = {'above_content': render_to_string(template_name='pending_task_list_ajax.html')}
        extra_context.update(kwargs.get('update_params', {}))
        default_dispatch(instance=self, extra_context=extra_context)
        return super(CswIndexView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return get_queryset_filter_by_service_type(instance=self, service_type=OGCServiceEnum.CSW)


class DatasetIndexView(SingleTableMixin, FilterView):
    model = Metadata
    table_class = DatasetTable
    filterset_class = DatasetFilter

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(DatasetIndexView, self).get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.DATASET.value]}) + _(' Dataset')

        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
                                     update_url_qs=get_current_view_args(self.request))
        table.actions = [render_helper.render_item(item=Metadata.get_add_dataset_action())]
        return table

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self, extra_context=kwargs.get('update_params', {}))
        return super(DatasetIndexView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.get_datasets_as_qs(user_groups=self.request.user.get_groups())


class ResourceView(TemplateView):
    """
    This is the wrapper view, you include the inline view inside the
    wrapper view get_context_data.
    """
    template_name = "generic_views/wrapper_template.html"

    def get_context_data(self, **kwargs):
        context = super(ResourceView, self).get_context_data(**kwargs)
        context.update(kwargs.get('update_params', {}))
        context = DefaultContext(request=self.request, context=context).get_context()

        self.request.GET._mutable = True
        self.request.GET.update({'with-base': False})
        self.request.GET._mutable = False

        rendered_wms_view = WmsIndexView.as_view()(request=self.request)
        rendered_wfs_view = WfsIndexView.as_view()(request=self.request)
        rendered_csw_view = CswIndexView.as_view()(request=self.request)
        rendered_dataset_view = DatasetIndexView.as_view()(request=self.request)
        rendered_pending_task_ajax = render_to_string(template_name='pending_task_list_ajax.html')

        context['inline_html_items'] = [rendered_pending_task_ajax,
                                        rendered_wms_view.rendered_content,
                                        rendered_wfs_view.rendered_content,
                                        rendered_csw_view.rendered_content,
                                        rendered_dataset_view.rendered_content,]
        return context


def _is_updatecandidate(metadata: Metadata):
    # get service object
    if metadata.is_metadata_type(MetadataEnum.FEATURETYPE):
        service = metadata.featuretype.parent_service
    elif metadata.is_metadata_type(MetadataEnum.DATASET):
        return False
    else:
        service = metadata.service
    # proof if the requested metadata is a update_candidate --> 404
    if service.is_root:
        if service.is_update_candidate_for is not None:
            return True
    else:
        if service.parent_service.is_update_candidate_for is not None:
            return True
    return False


@login_required
@check_permission(
    PermissionEnum.CAN_REGISTER_RESOURCE
)
def add(request: HttpRequest):
    """ Renders wizard page configuration for service registration

        Args:
            request (HttpRequest): The incoming request
        Returns:
             params (dict): The rendering parameter
    """
    return NewResourceWizard.as_view(
        form_list=NEW_RESOURCE_WIZARD_FORMS,
        current_view=request.GET.get('current-view'),
        title=_l(format_html('<b>Add New Resource</b>')),
        id_wizard='add_new_resource_wizard',
    )(request=request)

@login_required
@check_permission(
    PermissionEnum.CAN_REMOVE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
def remove(request: HttpRequest, metadata_id):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
        metadata_id:
    Returns:
        Redirect to service:index
    """
    metadata = get_object_or_404(Metadata, id=metadata_id)
    form = RemoveServiceForm(data=request.POST or None,
                             request=request,
                             reverse_lookup='resource:remove',
                             reverse_args=[metadata_id, ],
                             # ToDo: after refactoring of all forms is done, show_modal can be removed
                             show_modal=True,
                             is_confirmed_label=_l("Do you really want to remove this service?"),
                             form_title=_l(f"Remove service <strong>{metadata}</strong>"),
                             instance=metadata)
    return form.process_request(valid_func=form.process_remove_service)


@login_required
@resolve_metadata_public_id
@check_permission(
    PermissionEnum.CAN_ACTIVATE_RESOURCE
)
@check_ownership(Metadata, 'pk')
def activate(request: HttpRequest, pk):
    """ (De-)Activates a service and all of its layers

    Args:
        pk:
        request:
    Returns:
         redirects to service:index
    """
    md = get_object_or_404(Metadata, id=pk)

    form = ActivateServiceForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='resource:activate',
        reverse_args=[pk, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_l("Deactivate resource \n<strong>{}</strong>").format(md.title) if md.is_active else _l("Activate resource \n<strong>{}</strong>").format(md.title),
        is_confirmed_label=_l("Do you really want to deactivate this resource?") if md.is_active else _l("Do you really want to activate this resource?"),
        instance=md,
    )
    return form.process_request(valid_func=form.process_activate_service)


@resolve_metadata_public_id
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
    user = user_helper.get_user(request)
    subscription_created = Subscription.objects.get_or_create(
        metadata=md,
        user=user,
    )[1]
    if subscription_created:
        messages.success(request, SUBSCRIPTION_CREATED_TEMPLATE.format(md.title))
    else:
        messages.info(request, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE.format(md.title))

    return redirect("subscription-index")


@resolve_metadata_public_id
def get_dataset_metadata(request: HttpRequest, metadata_id):
    """ Returns the dataset metadata xml file for a given metadata id

    Args:
        metadata_id: The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    md = get_object_or_404(Metadata, id=metadata_id)
    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)
    try:
        if md.metadata_type != OGCServiceEnum.DATASET.value:
            # the user gave the metadata id of the service metadata, we must resolve this to the related dataset metadata
            md = md.get_related_dataset_metadata()
            if md is None:
                raise ObjectDoesNotExist
            return redirect("resource:get-dataset-metadata", metadata_id=md.id)
        documents = Document.objects.filter(
            metadata=md,
            document_type=DocumentEnum.METADATA.value,
            is_active=True,
        )
        # prefer current metadata document (is_original=false), otherwise take the original one
        document = documents.get(is_original=False) if documents.filter(is_original=False).exists() else documents.get(is_original=True)
        document = document.content
    except ObjectDoesNotExist:
        # ToDo: a datasetmetadata without a document is broken
        return HttpResponse(content=_l("No dataset metadata found"), status=404)
    return HttpResponse(document, content_type='application/xml')


@resolve_metadata_public_id
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
            not md.service.is_service_type(OGCServiceEnum.WMS) or _is_updatecandidate(md):
        return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

    if md.service.is_service_type(OGCServiceEnum.WMS) and md.service.is_root:
        service = get_object_or_404(Service, id=md.service.id)
        layer = get_object_or_404(Layer, parent_service=service, parent_layer=None, )
        # Fake the preview image for the whole service by using the root layer instead
        md = layer.metadata
    elif md.service.is_service_type(OGCServiceEnum.WMS) and not md.service.is_root:
        layer = md.service.layer

    layer = layer.identifier
    if md.bounding_geometry.area == 0:
        bbox = md.find_max_bounding_box()
    else:
        bbox = md.bounding_geometry
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


@resolve_metadata_public_id
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


@resolve_metadata_public_id
def get_metadata_html(request: HttpRequest, metadata_id):
    """ Returns the metadata as html rendered view
        Args:
            request (HttpRequest): The incoming request
            metadata_id : The metadata id
        Returns:
             A HttpResponse containing the html formated metadata
    """
    # ---- constant values
    base_template = '404.html'
    # ----
    md = get_object_or_404(Metadata, id=metadata_id)
    if _is_updatecandidate(md):
        return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

    # collect global data for all cases
    params = {
        'md_id': md.id,
        'title': md.title,
        'abstract': md.abstract,
        'access_constraints': md.access_constraints,
        'capabilities_original_uri': md.capabilities_original_uri,
        'capabilities_uri': md.capabilities_uri,
        'contact': collect_contact_data(md.contact),
        "SEMANTIC_WEB_HTML_INFORMATION": SEMANTIC_WEB_HTML_INFORMATION,
    }

    params.update(collect_metadata_related_objects(md, request, ))

    # build the single view cases: wms root, wms layer, wfs root, wfs featuretype, wcs, metadata
    if md.is_metadata_type(MetadataEnum.DATASET):
        base_template = 'metadata/base/dataset/dataset_metadata_as_html.html'
        params['contact'] = collect_contact_data(md.contact)
        params['bounding_box'] = md.bounding_geometry
        params['dataset_metadata'] = md
        params['fees'] = md.fees
        params['licence'] = md.licence
        params.update({'capabilities_uri': md.service_metadata_uri})

    elif md.is_metadata_type(MetadataEnum.FEATURETYPE):
        base_template = 'metadata/base/wfs/featuretype_metadata_as_html.html'
        params.update(collect_featuretype_data(md))

    elif md.is_metadata_type(MetadataEnum.LAYER):
        base_template = 'metadata/base/wms/layer_metadata_as_html.html'
        params.update(collect_layer_data(md, request))

    elif md.service.is_service_type(OGCServiceEnum.WMS):
        # wms root object
        base_template = 'metadata/base/wms/root_metadata_as_html.html'
        params.update(collect_wms_root_data(md, request))

    elif md.service.is_service_type(OGCServiceEnum.WFS):
        # wfs root object
        base_template = 'metadata/base/wfs/root_metadata_as_html.html'
        params.update(collect_wfs_root_data(md, request))

    elif md.is_catalogue_metadata:
        # ToDo: Add html view for CSW!
        pass

    context = DefaultContext(request, params, None)
    return render(request=request, template_name=base_template, context=context.get_context())


@login_required
@check_permission(
    PermissionEnum.CAN_UPDATE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
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
    user = user_helper.get_user(request)

    form = UpdateServiceCheckForm(data=request.POST or None,
                                  request=request,
                                  reverse_lookup='resource:new-pending-update',
                                  reverse_args=[metadata_id, ],
                                  # ToDo: after refactoring of all forms is done, show_modal can be removed
                                  show_modal=True,
                                  current_service=current_service,
                                  requesting_user=user,
                                  form_title=_l(f'Update service: <strong>{current_service.metadata.title} [{current_service.metadata.id}]</strong>'))
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
@check_permission(
    PermissionEnum.CAN_UPDATE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
@transaction.atomic
def pending_update_service(request: HttpRequest, metadata_id, update_params: dict = None, status_code: int = 200, ):
    template = "views/service_update.html"
    user = user_helper.get_user(request)

    current_service = get_object_or_404(Service, metadata__id=metadata_id)
    try:
        new_service = Service.objects.get(is_update_candidate_for=current_service)
    except ObjectDoesNotExist:
        messages.error(request, _l("No updatecandidate was found."))
        # ToDo: make 7 dynamic
        messages.info(request, _l("Update candidates will be deleted after 7 days."))
        return HttpResponseRedirect(reverse("resource:detail", args=(metadata_id,)), status=303)

    if current_service.is_service_type(OGCServiceEnum.WMS):
        current_service.root_layer = Layer.objects.get(parent_service=current_service, parent_layer=None)
        new_service.root_layer = Layer.objects.get(parent_service=new_service, parent_layer=None)

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
                                                   order_by_field='updated',)

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

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
@check_permission(
    PermissionEnum.CAN_UPDATE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
@transaction.atomic
def dismiss_pending_update_service(request: HttpRequest, metadata_id):
    user = user_helper.get_user(request)
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
@check_permission(
    PermissionEnum.CAN_UPDATE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
@transaction.atomic
def run_update_service(request: HttpRequest, metadata_id):
    user = user_helper.get_user(request)

    if request.method == 'POST':
        current_service = get_object_or_404(Service, metadata__id=metadata_id)
        new_service = get_object_or_404(Service, is_update_candidate_for=current_service)
        new_document = get_object_or_404(
            Document,
            metadata=new_service.metadata,
            document_type=DocumentEnum.CAPABILITY.value,
            is_original=True,
        )

        if not current_service.is_service_type(OGCServiceEnum.WFS):
            new_service.root_layer = get_object_or_404(Layer, parent_service=new_service, parent_layer=None)
            current_service.root_layer = get_object_or_404(Layer, parent_service=current_service, parent_layer=None)

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

            # Then update the service object
            current_service = update_helper.update_service(current_service, new_service)

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
                # dauer lange
                current_service = update_helper.update_wms_elements(
                    current_service,
                    new_service,
                    diff,
                    links,
                    new_service.keep_custom_md
                )

            update_helper.update_capability_document(current_service, new_document.content)

            current_service.save()
            user_helper.create_group_activity(
                current_service.metadata.created_by,
                user,
                SERVICE_UPDATED,
                current_service.metadata.title
            )

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


def _check_for_dataset_metadata(metadata: Metadata, ):
    """ Checks whether a metadata object has a dataset metadata record.

    Args:
        metadata:
    Returns:
         The document or none
    """
    try:
        md_2 = metadata.get_related_dataset_metadata()
        return Document.objects.get(
            metadata=md_2,
            document_type=DocumentEnum.METADATA.value,
        )
    except ObjectDoesNotExist:
        return None


class ResourceDetailTableView(DetailView):
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


class ResourceRelatedDatasetView(DetailView):
    model = Metadata
    template_name = 'generic_views/generic_detail_without_base.html'
    queryset = Metadata.objects.all().prefetch_related('related_metadata',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        related_datasets = self.object.get_related_dataset_metadata()

        if related_datasets:
            item_list = []
            for related_dataset in related_datasets:
                link_to_dataset = Link(url=related_dataset.detail_view_uri, content=related_dataset.title)

                metadata_xml = Link(url=related_dataset.service_metadata_uri,
                                    content=FONT_AWESOME_ICONS['CAPABILITIES'] + _(' XML'),
                                    open_in_new_tab=True)
                metadata_html = Link(url=related_dataset.html_metadata_uri,
                                     content=FONT_AWESOME_ICONS['NEWSPAPER'] + _(' HTML'),
                                     open_in_new_tab=True)

                dataset_metadata_dropdown = Dropdown(btn_value=FONT_AWESOME_ICONS['METADATA'] + _(' Metadata'),
                                                     items=[metadata_xml, metadata_html],
                                                     color=ButtonColorEnum.SECONDARY,
                                                     header=_l('Show metadata as:'))

                render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
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


class ResourceTreeView(DetailView):
    model = Metadata
    template_name = 'generic_views/generic_detail_with_base.html'
    # todo: filter all update candidates here
    # todo: prefetch_related
    queryset = Metadata.objects.filter(service__is_update_candidate_for=None)

    def dispatch(self, request, *args, **kwargs):
        default_dispatch(instance=self, extra_context=kwargs.get('update_params', {}), is_list_view=False)
        return super(ResourceTreeView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'tree_style': True})
        render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())),
                                     update_url_qs=get_current_view_args(self.request),
                                     update_attrs={"class": ["btn-sm", "mr-1"]})
        actions = self.object.get_actions()
        context['object'].actions = render_helper.render_list_coherent(items=actions)

        card_body = ''
        root_details = None
        capabilities_dropdown = None
        sub_elements = None
        if self.object.is_metadata_type(MetadataEnum.SERVICE):
            root_details = Modal(title=f'Details of {self.object.title}',
                                 body='',
                                 fetch_url=reverse('resource:detail-table', args=[self.object.pk]),
                                 btn_content=Tag(tag='i', attrs={"class": [IconEnum.INFO.value]}) + _(' Details'),
                                 btn_attrs={"class": [ButtonColorEnum.SECONDARY.value, "mr-1"]},
                                 btn_tooltip=_l('Open details'),
                                 size=ModalSizeEnum.LARGE,)

            capabilities_original = Link(url=self.object.capabilities_original_uri, content=_('Original'),
                                         open_in_new_tab=True)
            capabilities_current = Link(url=self.object.capabilities_uri, content=_('Current'),
                                        open_in_new_tab=True)
            capabilities_dropdown = Dropdown(btn_value=Tag(tag='i', attrs={"class": [IconEnum.CAPABILITIES.value]}) + _(' Capabilities'),
                                             items=[capabilities_original, capabilities_current],
                                             color=ButtonColorEnum.SECONDARY,
                                             tooltip=_l('Show capabilities'),
                                             header=_l('See current or original:'),
                                             btn_attrs={"class": ['mr-1']})

            if self.object.is_service_type(enum=OGCServiceEnum.WMS):
                context['object'].title = Tag(tag='i', attrs={"class": [IconEnum.WMS.value]}) + f" {context['object'].title}"
                sub_elements = Layer.objects.filter(parent_service=self.object.service,
                                                    parent_layer=None).prefetch_related('metadata')

            elif self.object.is_service_type(enum=OGCServiceEnum.WFS):
                context['object'].title = Tag(tag='i', attrs={"class": [IconEnum.WFS.value]}) + f" {context['object'].title}"
                sub_elements = self.object.service.featuretypes.all().prefetch_related('elements')

        elif self.object.is_metadata_type(MetadataEnum.FEATURETYPE):
            context['object'].title = Tag(tag='i', attrs={"class": [IconEnum.FEATURETYPE.value]}) + f" {context['object'].title}"
            sub_elements = self.object.featuretype.elements.all()

        elif self.object.is_metadata_type(MetadataEnum.LAYER):
            context['object'].title = Tag(tag='i', attrs={"class": [IconEnum.LAYER.value]}) + f" {context['object'].title}"
            sub_elements = Layer.objects.filter(parent_layer=self.object.service).prefetch_related('metadata')

        if sub_elements:
            sub_element_accordions = ''
            if isinstance(sub_elements.first(), FeatureTypeElement):
                elements_table = FeatureTypeElementTable(data=sub_elements, orderable=False)
                sub_element_accordions += render_to_string(template_name='skeletons/django_tables2_bootstrap4_custom.html',
                                                           context={'table': elements_table})
            else:
                for sub_element in sub_elements:
                    details = Modal(title=f'Details of {sub_element.metadata.title}',
                                    body='',
                                    btn_content=Tag(tag='i', attrs={"class": [IconEnum.INFO.value]}) + _(' Details'),
                                    btn_attrs={"class": [ButtonColorEnum.SECONDARY.value, "mr-1"]},
                                    btn_tooltip=_l('Open details'),
                                    fetch_url=sub_element.metadata.detail_table_view_uri,
                                    size=ModalSizeEnum.LARGE)

                    metadata_xml = Link(url=sub_element.metadata.service_metadata_uri,
                                        content=Tag(tag='i', attrs={"class": [IconEnum.CAPABILITIES.value]}) + _(' XML'),
                                        open_in_new_tab=True)
                    metadata_html = Link(url=sub_element.metadata.html_metadata_uri,
                                         content=Tag(tag='i', attrs={"class": [IconEnum.NEWSPAPER.value]}) + _(' HTML'),
                                         open_in_new_tab=True)
                    metadata_dropdown = Dropdown(btn_value=Tag(tag='i', attrs={"class": [IconEnum.METADATA.value]}) + _(' Metadata'),
                                                 items=[metadata_xml, metadata_html],
                                                 color=ButtonColorEnum.SECONDARY,
                                                 tooltip=_l('Show metadata'),
                                                 header=_l('Show metadata as:'),
                                                 btn_attrs={"class": ["mr-1"]})

                    sub_element_icon = ''
                    if sub_element.metadata.is_metadata_type(MetadataEnum.LAYER):
                        sub_element_icon = FONT_AWESOME_ICONS['LAYER'] + ' '
                        sub_sub_elements_count = Layer.objects.filter(parent_layer=sub_element).count()
                    elif sub_element.metadata.is_metadata_type(MetadataEnum.FEATURETYPE):
                        sub_element_icon = FONT_AWESOME_ICONS['FEATURETYPE'] + ' '
                        sub_sub_elements_count = sub_element.elements.count()

                    accordion_title = sub_element_icon + sub_element.metadata.title + ' ' + Badge(content=sub_sub_elements_count)
                    accordion_title_center = f'{details}{details.button}{metadata_dropdown}'

                    related_datasets = sub_element.metadata.get_related_dataset_metadata(count=True)
                    if related_datasets > 0:
                        dataset_modal = Modal(title=_l('Related datasets of ') + sub_element.metadata.title, body='',
                                              fetch_url=sub_element.metadata.detail_related_datasets_view_uri,
                                              btn_content=Tag(tag='i', attrs={"class": [IconEnum.METADATA.value]}) + _(' Datasets ') + Badge(content=related_datasets),
                                              btn_attrs={"class": [ButtonColorEnum.SECONDARY.value]},
                                              size=ModalSizeEnum.LARGE)
                        accordion_title_center += dataset_modal.button + dataset_modal

                    if sub_sub_elements_count > 0:
                        sub_element_accordions += Accordion(btn_value=accordion_title,
                                                            header_center_content=accordion_title_center,
                                                            header_right_content=render_helper.render_list_coherent(items=sub_element.metadata.get_actions()),
                                                            fetch_url=sub_element.metadata.detail_view_uri + '?with-base=False',
                                                            card_attrs={"style": ["overflow: inherit;"],
                                                                        "class": ["mb-1"]})
                    else:
                        content = DefaultHeaderRow(content_left=accordion_title,
                                                   content_center=accordion_title_center,
                                                   content_right=render_helper.render_list_coherent(items=sub_element.metadata.get_actions()))
                        card_header = CardHeader(content=content.render())
                        card_header.update_attributes(update_attrs={"class": ["mb-1"]})
                        sub_element_accordions += card_header

            card_body += sub_element_accordions

        metadata_xml = Link(url=self.object.service_metadata_uri,
                            content=Tag(tag='i', attrs={"class": [IconEnum.CAPABILITIES.value]}) + _(' XML'),
                            open_in_new_tab=True)
        metadata_html = Link(url=self.object.html_metadata_uri,
                             content=Tag(tag='i', attrs={"class": [IconEnum.NEWSPAPER.value]}) + _(' HTML'),
                             open_in_new_tab=True)
        metadata_dropdown = Dropdown(btn_value=Tag(tag='i', attrs={"class": [IconEnum.METADATA.value]}) + _(' Metadata'),
                                     color=ButtonColorEnum.SECONDARY,
                                     items=[metadata_xml, metadata_html],
                                     tooltip=_l('Show metadata'),
                                     header=_l('Show metadata as:'))

        card_header_title_center = root_details.button+root_details if root_details else ''
        card_header_title_center += capabilities_dropdown if capabilities_dropdown else ''
        card_header_title_center += metadata_dropdown

        context.update({
            'card_header_title_left': context['object'].title,
            'card_header_title_center': card_header_title_center,
            'card_header_title_right': render_helper.render_list_coherent(items=actions),
            'card_body': card_body
        })
        context = DefaultContext(request=self.request, context=context).get_context()
        return context


@csrf_exempt
@resolve_metadata_public_id
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
    get_query_string = request.environ.get("QUERY_STRING", "")

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
            response_dict = operation_handler.get_secured_operation_response(request, metadata, proxy_log=proxy_log)
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
    except Exception as e:
        return HttpResponse(status=500, content=e)


@resolve_metadata_public_id
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


@login_required
@check_permission(
    PermissionEnum.CAN_ACCESS_LOGS
)
def logs_view(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a view for the ProxyLog entries

    Possible parameters for log filtering are:
        * ds (date-start): Date-time string
        * de (date-end): Date-time string
        * u (user): Id of a user
        * g (group): Id of a group
        * t (type): 'wms'|'wfs'

    Args:
        request (HttpRequest):
    Returns:

    """
    template = "views/log_index.html"
    user = user_helper.get_user(request)

    params = {
        "log_table": prepare_proxy_log_filter(
            request=request,
            user=user,
            current_view='resource:logs-view'
        ),
        "current_view": 'resource:logs-view',
    }
    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context(), status=status_code)


@login_required
@check_permission(
    PermissionEnum.CAN_DOWNLOAD_LOGS
)
def logs_download(request: HttpRequest):
    """ Provides the filtered ProxyLog table as csv download.

    CSV is the only provided file type.

    Args:
        request (HttpRequest):
    Returns:

    """
    user = user_helper.get_user(request)
    CSV = "text/csv"
    # ToDo: current_view parameter should be dynamic
    proxy_log_table = prepare_proxy_log_filter(request=request, user=user, current_view='resource:logs-view')

    # Create empty response object and fill it with dynamic csv content
    stream = io.StringIO()
    timestamp_now = timezone.now()
    data = proxy_log_table.fill_csv_response(stream)

    data_size = len(data)
    # Stream files larger than 100 MB
    if data_size > 100 * 1024 * 1024:
        response = StreamingHttpResponse(data, content_type=CSV)
    else:
        response = HttpResponse(data, content_type=CSV)

    response['Content-Disposition'] = f'attachment; filename="MrMap_logs_{timestamp_now.strftime("%Y-%m-%dT%H:%M:%S")}.csv"'
    return response
