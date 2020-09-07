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
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from requests.exceptions import ReadTimeout
from django.utils import timezone
from MrMap.cacher import PreviewImageCacher
from MrMap.consts import *
from MrMap.decorator import check_permission, log_proxy, check_ownership, resolve_metadata_public_id
from MrMap.messages import SERVICE_UPDATED, \
    SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED, SERVICE_LAYER_NOT_FOUND, \
    SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT, SERVICE_CAPABILITIES_UNAVAILABLE, \
    SUBSCRIPTION_CREATED_TEMPLATE, SUBSCRIPTION_ALREADY_EXISTS_TEMPLATE
from MrMap.responses import DefaultContext
from MrMap.settings import SEMANTIC_WEB_HTML_INFORMATION
from service.filters import MetadataWmsFilter, MetadataWfsFilter, MetadataDatasetFilter, MetadataCswFilter
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
from service.tables import WmsTableWms, WmsLayerTableWms, WfsServiceTable, PendingTasksTable, UpdateServiceElements, \
    DatasetTable, CswTable
from service.tasks import async_log_response
from service.models import Metadata, Layer, Service, Document, Style, ProxyLog
from service.utils import collect_contact_data, collect_metadata_related_objects, collect_featuretype_data, \
    collect_layer_data, collect_wms_root_data, collect_wfs_root_data
from service.wizards import NEW_RESOURCE_WIZARD_FORMS, NewResourceWizard
from structure.models import MrMapUser, PendingTask
from structure.permissionEnums import PermissionEnum
from users.helper import user_helper
from django.urls import reverse

from users.models import Subscription


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


def _prepare_wms_table(request: HttpRequest, current_view: str, user_groups):
    """ Collects all wms service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
    Returns:
         params (dict): The rendering parameter
    """
    # whether whole services or single layers should be displayed
    if 'show_layers' in request.GET and request.GET.get("show_layers").lower() == 'on':
        show_service = False
    else:
        show_service = True

    queryset = Metadata.objects.filter(
        service__service_type__name=OGCServiceEnum.WMS.value,
        created_by__in=user_groups,
        is_deleted=False,
        service__is_update_candidate_for=None
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

    if show_service:
        wms_table = WmsTableWms(request=request,
                                queryset=queryset,
                                filter_set_class=MetadataWmsFilter,
                                order_by_field='swms',  # swms = sort wms
                                current_view=current_view,
                                param_lead='wms-t', )
    else:
        wms_table = WmsLayerTableWms(request=request,
                                     queryset=queryset,
                                     filter_set_class=MetadataWmsFilter,
                                     order_by_field='swms',  # swms = sort wms
                                     current_view=current_view,
                                     param_lead='wms-t', )

    return {
        "wms_table": wms_table,
    }


def _prepare_wfs_table(request: HttpRequest, current_view: str, user_groups):
    """ Collects all wfs service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    queryset = Metadata.objects.filter(
        service__service_type__name=OGCServiceEnum.WFS.value,
        created_by__in=user_groups,
        is_deleted=False,
        service__is_update_candidate_for=None
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

    wfs_table = WfsServiceTable(request=request,
                                queryset=queryset,
                                filter_set_class=MetadataWfsFilter,
                                order_by_field='swfs',  # swms = sort wms
                                current_view=current_view,
                                param_lead='wfs-t',)

    return {
        "wfs_table": wfs_table,
    }


def _prepare_csw_table(request: HttpRequest, current_view: str, user_groups):
    """ Collects all wfs service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    queryset = Metadata.objects.filter(
        metadata_type=MetadataEnum.CATALOGUE.value,
        created_by__in=user_groups,
        is_deleted=False,
        service__is_update_candidate_for=None
    ).prefetch_related(
        "contact",
        "service",
        "service__created_by",
        "service__published_for",
        "service__service_type",
        "external_authentication",
    ).order_by("title")

    table = CswTable(request=request,
                     queryset=queryset,
                     filter_set_class=MetadataCswFilter,
                     order_by_field='scsw',  # scsw = sort csw
                     current_view=current_view,
                     param_lead='csw-t',)

    return {
        "csw_table": table,
    }


def _prepare_dataset_table(request: HttpRequest, user: MrMapUser, current_view: str, user_groups):
    dataset_table = DatasetTable(request=request,
                                 filter_set_class=MetadataDatasetFilter,
                                 queryset=user.get_datasets_as_qs(user_groups=user_groups),
                                 current_view=current_view,
                                 param_lead='dataset-t',)
    return {
            "dataset_table": dataset_table,
    }


@login_required
@check_permission(
    PermissionEnum.CAN_REGISTER_RESOURCE
)
def add(request: HttpRequest):
    """ Renders wizard page configuration for service registration

        Args:
            request (HttpRequest): The incoming request
            user (User): The performing user
        Returns:
             params (dict): The rendering parameter
    """
    return NewResourceWizard.as_view(
        form_list=NEW_RESOURCE_WIZARD_FORMS,
        current_view=request.GET.get('current-view'),
        title=_(format_html('<b>Add New Resource</b>')),
        id_wizard='add_new_resource_wizard',
    )(request=request)


@login_required
def index(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        update_params: (Optional) the update_params dict
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "views/index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user_groups).order_by('id')
    pt_table = PendingTasksTable(data=pt,
                                 orderable=False,
                                 request=request,)

    params = {
        "pt_table": pt_table,
        "current_view": "resource:index",
    }

    params.update(_prepare_wms_table(request=request, current_view='resource:index', user_groups=user_groups))
    params.update(_prepare_wfs_table(request=request, current_view='resource:index', user_groups=user_groups))
    params.update(_prepare_csw_table(request=request, current_view='resource:index', user_groups=user_groups))
    params.update(_prepare_dataset_table(request=request, current_view='resource:index', user=user, user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def pending_tasks(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a table of all pending tasks without any css depending scripts or something else

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    # Default content
    template = "includes/pending_tasks.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.get_groups()).order_by('id')
    pt_table = PendingTasksTable(data=pt,
                                 orderable=False,
                                 request=request,)
    params = {
        "pt_table": pt_table,
        "current_view": "resource:prending-tasks",
    }

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)

@login_required
def wms_table(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a table of all wms without any css depending scripts or something else

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "includes/index/wms.html"

    current_view = request.GET.get('current-view', None)

    params = {
        "current_view": current_view,
    }

    params.update(_prepare_wms_table(request=request, current_view=current_view, user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def wfs_table(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a table of all wfs without any css depending scripts or something else

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "includes/index/wfs.html"

    current_view = request.GET.get('current-view', None)

    params = {
        "current_view": current_view,
    }

    params.update(_prepare_wfs_table(request=request, current_view=current_view, user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def csw_table(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a table of all csw without any css depending scripts or something else

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "includes/index/csw.html"

    current_view = request.GET.get('current-view', None)

    params = {
        "current_view": current_view,
    }

    params.update(_prepare_csw_table(request=request, current_view=current_view, user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def datasets_table(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders a table of all datasets without any css depending scripts or something else

    Args:
        request (HttpRequest): The incoming request
        update_params:
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "includes/index/datasets.html"

    current_view = request.GET.get('current-view', None)

    params = {
        "current_view": current_view,
    }

    params.update(_prepare_dataset_table(request=request, current_view=current_view, user_groups=user_groups, user=user))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


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
                             is_confirmed_label=_("Do you really want to remove this service?"),
                             form_title=_(f"Remove service <strong>{metadata}</strong>"),
                             instance=metadata)
    return form.process_request(valid_func=form.process_remove_service)


@login_required
@resolve_metadata_public_id
@check_permission(
    PermissionEnum.CAN_ACTIVATE_RESOURCE
)
@check_ownership(Metadata, 'metadata_id')
def activate(request: HttpRequest, metadata_id):
    """ (De-)Activates a service and all of its layers

    Args:
        metadata_id:
        request:
    Returns:
         redirects to service:index
    """
    md = get_object_or_404(Metadata, id=metadata_id)

    form = ActivateServiceForm(
        data=request.POST or None,
        request=request,
        reverse_lookup='resource:activate',
        reverse_args=[metadata_id, ],
        # ToDo: after refactoring of all forms is done, show_modal can be removed
        show_modal=True,
        form_title=_("Deactivate resource \n<strong>{}</strong>").format(md.title) if md.is_active else _("Activate resource \n<strong>{}</strong>").format(md.title),
        is_confirmed_label=_("Do you really want to deactivate this resource?") if md.is_active else _("Do you really want to activate this resource?"),
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
        return HttpResponse(content=_("No dataset metadata found"), status=404)
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
def wms_index(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of all wms

    Args:t
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "views/wms_index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user_groups).order_by('id')
    pt_table = PendingTasksTable(data=pt,
                                 orderable=False,
                                 request=request,)

    params = {
        "pt_table": pt_table,
        "current_view": "resource:wms-index",
    }

    params.update(_prepare_wms_table(request=request, current_view='resource:wms-index', user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
def csw_index(request: HttpRequest, update_params: dict = None, status_code: int = 200, ):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        update_params: (Optional) the update_params dict
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "views/csw_index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user_groups).order_by('id')
    pt_table = PendingTasksTable(data=pt,
                                 orderable=False,
                                 request=request,)

    params = {
        "pt_table": pt_table,
        "current_view": "resource:csw-index",
    }

    params.update(_prepare_csw_table(request=request, current_view='resource:index', user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=status_code)


@login_required
@check_permission(
    PermissionEnum.CAN_EDIT_METADATA
)
def datasets_index(request: HttpRequest, update_params=None, status_code: int = 200, ):
    """ The index view of the editor app.

    Lists all datasets with information of custom set metadata.

    Args:
        request: The incoming request
        update_params:
        status_code:
    Returns:
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    template = "views/datasets_index.html"

    params = {
        "current_view": 'resource:datasets-index',
    }
    params.update(
        _prepare_dataset_table(
            request=request,
            user=user,
            current_view='resource:datasets-index',
            user_groups=user_groups
        ),
    )

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
                                  form_title=_(f'Update service: <strong>{current_service.metadata.title} [{current_service.metadata.id}]</strong>'))
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
        messages.error(request, _("No updatecandidate was found."))
        # ToDo: make 7 dynamic
        messages.info(request, _("Update candidates will be deleted after 7 days."))
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
            messages.success(request, _("Pending update successfully dismissed."))
        else:
            messages.error(request, _("You are not the owner of this pending update. Rejected!"))

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


@login_required
def wfs_index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)
    user_groups = user.get_groups()

    # Default content
    template = "views/wfs_index.html"

    # get pending tasks
    pending_tasks = PendingTask.objects.filter(created_by__in=user_groups).order_by('id')
    pt_table = PendingTasksTable(data=pending_tasks,
                                 orderable=False,
                                 request=request,)

    params = {
        "pt_table": pt_table,
        "current_view": "resource:wfs-index"
    }

    params.update(_prepare_wfs_table(request=request, current_view='resource:wfs-indext', user_groups=user_groups))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


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

# Todo: index view
@login_required
@check_ownership(Metadata, 'object_id')
def detail(request: HttpRequest, object_id, update_params=None, status_code=None):
    """ Renders a detail view of the selected service

    Args:
        request: The incoming request
        object_id: The id of the selected metadata
        update_params: dict with params we will update before we return the context
        status_code
    Returns:
    """
    user = user_helper.get_user(request)

    template = "views/detail.html"
    service_md = get_object_or_404(Metadata, id=object_id)

    if _is_updatecandidate(service_md):
        return HttpResponse(status=404, content=SERVICE_NOT_FOUND)

    params = {}

    # catch featuretype
    if service_md.is_metadata_type(MetadataEnum.FEATURETYPE):
        params.update({'caption': _("Shows informations about the featuretype.")})
        template = "views/featuretype_detail_no_base.html" if 'no-base' in request.GET else "views/featuretype_detail.html"
        service = service_md.featuretype
        layers_md_list = {}
        params.update({'has_dataset_metadata': _check_for_dataset_metadata(service.metadata)})
    else:
        if service_md.service.is_root:
            params.update({'caption': _("Shows informations about the service.")})
            service = service_md.service
            layers = Layer.objects.filter(parent_service=service_md.service)
            layers_md_list = layers.filter(parent_layer=None)
        else:
            params.update({'caption': _("Shows informations about the sublayer.")})
            template = "views/sublayer_detail_no_base.html" if 'no-base' in request.GET else "views/sublayer_detail.html"
            service = Layer.objects.get(
                metadata=service_md
            )
            # get sublayers
            layers_md_list = Layer.objects.filter(
                parent_layer=service_md.service
            )
            params.update({'has_dataset_metadata': _check_for_dataset_metadata(service.metadata)})

    mime_types = {}

    formats = service_md.get_formats()
    for mime in formats:
        op = mime_types.get(mime.operation)
        if op is None:
            op = []
        op.append(mime.mime_type)
        mi = {mime.operation: op}
        mime_types.update(mi)

    params.update({
        "service_md": service_md,
        "service": service,
        "layers": layers_md_list,
        "mime_types": mime_types,
        "leaflet_add_bbox": True,
        "current_view": "resource:detail",
        "current_view_arg": object_id,
    })

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


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
