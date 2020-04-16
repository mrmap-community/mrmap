import io
import json
from io import BytesIO
from PIL import Image
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, QueryDict, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from requests import ReadTimeout
from MapSkinner import utils
from MapSkinner.cacher import PreviewImageCacher
from MapSkinner.consts import *
from MapSkinner.decorator import check_permission, log_proxy
from MapSkinner.messages import SERVICE_UPDATE_WRONG_TYPE, SERVICE_UPDATED, \
    SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED, SERVICE_LAYER_NOT_FOUND, \
    SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT, PARAMETER_ERROR, SERVICE_CAPABILITIES_UNAVAILABLE, \
    SERVICE_ACTIVATED, SERVICE_DEACTIVATED
from MapSkinner.responses import BackendAjaxResponse, DefaultContext

from service import tasks
from service.helper import xml_helper
from service.filters import WmsFilter, WfsFilter
from service.forms import RegisterNewServiceWizardPage1, \
    RegisterNewServiceWizardPage2, RemoveServiceForm, UpdateServiceCheckForm, UpdateOldToNewElementsForm
from service.helper import service_helper, update_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCOperationEnum, OGCServiceVersionEnum, MetadataEnum
from service.helper.ogc.operation_request_handler import OGCOperationRequestHandler
from service.helper.service_comparator import ServiceComparator
from service.settings import DEFAULT_SRS_STRING, PREVIEW_MIME_TYPE_DEFAULT
from service.tables import WmsServiceTable, WmsLayerTable, WfsServiceTable, PendingTasksTable
from service.tasks import async_increase_hits
from service.models import Metadata, Layer, Service, FeatureType, Document, MetadataRelation, Style, ProxyLog
from service.utils import collect_contact_data, collect_metadata_related_objects, collect_featuretype_data, \
    collect_layer_data, collect_wms_root_data, collect_wfs_root_data
from structure.models import MrMapUser, Permission, PendingTask, MrMapGroup
from users.helper import user_helper
from django.urls import reverse
from django import forms


def _prepare_wms_table(request: HttpRequest):
    """ Collects all wms service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    # whether whole services or single layers should be displayed
    user = user_helper.get_user(request)

    if 'show_layers' in request.GET and request.GET.get("show_layers").lower() == 'on':
        show_service = False
    else:
        show_service = True

    md_list_wms = Metadata.objects.filter(
        service__servicetype__name=OGCServiceEnum.WMS.value,
        service__is_root=show_service,
        created_by__in=user.get_groups(),
        is_deleted=False,
    ).order_by("title")

    wms_table_filtered = WmsFilter(request.GET, queryset=md_list_wms)

    if show_service:
        wms_table = WmsServiceTable(wms_table_filtered.qs,
                                    order_by_field='swms',  # swms = sort wms
                                    user=user,)
    else:
        wms_table = WmsLayerTable(wms_table_filtered.qs,
                                  order_by_field='swms',  # swms = sort wms
                                  user=user,)

    # add boolean field to filter.form; this is needed, cause the search form sends it if show layer dropdown is set
    # add it after table is created; otherwise we get a KeyError
    show_layers_ = forms.BooleanField(required=False, initial=False)
    wms_table_filtered.form.fields.update({'show_layers': show_layers_})

    wms_table.filter = wms_table_filtered
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    wms_table.configure_pagination(request, 'wms-t')

    params = {
        "wms_table": wms_table,
    }

    return params


def _prepare_wfs_table(request: HttpRequest):
    """ Collects all wfs service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (MrMapUser): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    user = user_helper.get_user(request)
    md_list_wfs = Metadata.objects.filter(
        service__servicetype__name=OGCServiceEnum.WFS.value,
        created_by__in=user.get_groups(),
        is_deleted=False,
    ).order_by("title")

    wfs_table_filtered = WfsFilter(request.GET, queryset=md_list_wfs)
    wfs_table = WfsServiceTable(wfs_table_filtered.qs,
                                order_by_field='swfs',  # swms = sort wms
                                user=user,)

    wfs_table.filter = wfs_table_filtered
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    wfs_table.configure_pagination(request, 'wfs-t')

    params = {
        "wfs_table": wfs_table,
    }

    return params


def _new_service_wizard_page1(request: HttpRequest):
    # Page One is posted --> validate it
    user = user_helper.get_user(request)
    form = RegisterNewServiceWizardPage1(request.POST)
    if form.is_valid():
        # Form is valid --> response with initialed page 2
        url_dict = service_helper.split_service_uri(form.cleaned_data['get_request_uri'])
        init_data = {
            'ogc_request': url_dict["request"],
            'ogc_service': url_dict["service"].value,
            'ogc_version': url_dict["version"],
            'uri': url_dict["base_uri"],
            'service_needs_authentication': False,
        }

        params = {
            "new_service_form": RegisterNewServiceWizardPage2(initial=init_data,
                                                              user=user,
                                                              selected_group=user.get_groups().first()),
            "show_new_service_form": True,
        }
        return index(request=request, update_params=params, status_code=202)
    else:
        # Form is not valid --> response with page 1 and show errors
        params = {
            "new_service_form": form,
            "show_new_service_form": True,
        }
        return index(request=request, update_params=params, status_code=422)


def _new_service_wizard_page2(request: HttpRequest):
    # Page two is posted --> collect all data from post and initial the form
    user = user_helper.get_user(request)
    selected_group = MrMapGroup.objects.get(id=int(request.POST.get("registering_with_group")))

    init_data = {'ogc_request': request.POST.get("ogc_request"),
                 'ogc_service': request.POST.get("ogc_service"),
                 'ogc_version': request.POST.get("ogc_version"),
                 'uri': request.POST.get("uri"),
                 'registering_with_group': request.POST.get("registering_with_group"),
                 'service_needs_authentication': request.POST.get("service_needs_authentication") == 'on',
                 'username': request.POST.get("username", None),
                 'password': request.POST.get("password", None),
                 }

    is_auth_needed = True if request.POST.get("service_needs_authentication") == 'on' else False

    # first check if it's just a update of the form
    if request.POST.get("is_form_update") == 'True':
        # reset update flag
        form = RegisterNewServiceWizardPage2(initial=init_data,
                                             user=user,
                                             selected_group=selected_group,
                                             service_needs_authentication=is_auth_needed,
                                             )
        # it's just a updated form state. return the new state as view
        params = {
            "new_service_form": form,
            "show_new_service_form": True,
        }
        return index(request=request, update_params=params,)
    else:
        # it's not a update. we have to validate the fields now
        # and if all is fine generate a new pending task object
        form = RegisterNewServiceWizardPage2(request.POST,
                                             initial=init_data,
                                             user=user,
                                             selected_group=selected_group,
                                             service_needs_authentication=is_auth_needed)

        if form.is_valid():
            try:
                # Run creation async!
                # Function returns the pending task object
                service_helper.create_new_service(form, user)

                # everthing works well. Redirect to index page.
                return HttpResponseRedirect(reverse("service:index",), status=303)
            except Exception as e:
                # Form is not valid --> response with page 2 and show errors
                form.add_error(None, e)
                params = {
                    "new_service_form": form,
                    "show_new_service_form": True,
                }
                return index(request=request, update_params=params, status_code=422)
        else:
            # Form is not valid --> response with page 2 and show errors
            params = {
                "new_service_form": form,
                "show_new_service_form": True,
            }
            return index(request=request, update_params=params, status_code=422)


@login_required
@check_permission(Permission(can_register_service=True))
def add(request: HttpRequest):
    """ Renders wizard page configuration for service registration

        Args:
            request (HttpRequest): The incoming request
            user (User): The performing user
        Returns:
             params (dict): The rendering parameter
    """
    if request.method == 'POST':
        page = int(request.POST.get("page"))
        if page == 1:
            return _new_service_wizard_page1(request)
        if page == 2:
            return _new_service_wizard_page2(request)

    return HttpResponseRedirect(reverse("service:index", ), status=303)


@login_required
def index(request: HttpRequest, update_params=None, status_code=None):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        update_params: (Optional) the update_params dict
        status_code:
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    # Default content
    template = "views/index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.get_groups())
    pt_table = PendingTasksTable(pt,
                                 orderable=False, user=user, )

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wms_table(request))
    params.update(_prepare_wfs_table(request))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@login_required
def pending_tasks(request: HttpRequest):
    """ Renders a table of all pending tasks

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    # Default content
    template = "includes/pending_tasks.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.get_groups())
    pt_table = PendingTasksTable(pt,
                                 orderable=False, user=user,)
    params = {
        "pt_table": pt_table,
        "user": user,
    }

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@login_required
@check_permission(Permission(can_remove_service=True))
def remove(request: HttpRequest, metadata_id: int):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
        metadata_id:
    Returns:
        Redirect to service:index
    """
    user = user_helper.get_user(request)
    metadata = get_object_or_404(Metadata, id=metadata_id)
    remove_form = RemoveServiceForm(request.POST)
    if request.method == 'POST':
        if remove_form.is_valid() and request.POST.get("is_confirmed") == 'on':
            service_helper.remove_service(metadata, user)
            return HttpResponseRedirect(reverse("service:index", ), status=303)
        else:
            params = {
                "remove_service_form": remove_form,
                "show_modal": True,
            }
            return detail(request=request, metadata_id=metadata_id, update_params=params, status_code=422)
    else:
        return HttpResponseRedirect(reverse("service:index", ), status=303)


@login_required
@check_permission(Permission(can_activate_service=True))
def activate(request: HttpRequest, service_id: int):
    """ (De-)Activates a service and all of its layers

    Args:
        service_id:
        request:
    Returns:
         redirects to service:index
    """
    user = user_helper.get_user(request)

    md = Metadata.objects.get(service__id=service_id)
    md.is_active = not md.is_active
    md.save()

    # run activation async!
    tasks.async_activate_service.delay(service_id, user.id, md.is_active)

    # If metadata WAS active, then it will be deactivated now
    if md.is_active:
        msg = SERVICE_ACTIVATED.format(md.title)
    else:
        msg = SERVICE_DEACTIVATED.format(md.title)
    messages.success(request, msg)

    return HttpResponseRedirect(reverse("service:detail", args=(md.id,)), status=303)


def get_service_metadata(request: HttpRequest, metadata_id: int):
    """ Returns the service metadata xml file for a given metadata id

    Args:
        metadata_id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    metadata = Metadata.objects.get(id=metadata_id)

    if not metadata.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    doc = metadata.get_service_metadata_xml()

    return HttpResponse(doc, content_type=APP_XML)


def get_dataset_metadata(request: HttpRequest, metadata_id: int):
    """ Returns the dataset metadata xml file for a given metadata id

    Args:
        metadata_id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    md = Metadata.objects.get(id=metadata_id)
    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)
    try:
        if md.metadata_type.type != OGCServiceEnum.DATASET.value:
            # the user gave the metadata id of the service metadata, we must resolve this to the related dataset metadata
            md = md.get_related_dataset_metadata()
            if md is None:
                raise ObjectDoesNotExist
            return redirect("service:get-dataset-metadata", metadata_id=md.id)
        document = Document.objects.get(related_metadata=md)
        document = document.dataset_metadata_document
        if document is None:
            raise ObjectDoesNotExist
    except ObjectDoesNotExist:
        return HttpResponse(content=_("No dataset metadata found"), status=404)
    return HttpResponse(document, content_type='application/xml')


def check_for_dataset_metadata(request: HttpRequest, metadata_id: int):
    """ Checks whether an element (layer or featuretype) has a dataset metadata record.

    This function is used for ajax calls from the client, to check dynamically on an opened subelement if there
    are dataset metadata to get.

    Args:
        request (HttpRequest): The incoming request
        metadata_id (int): The element id
    Returns:
         A BackendAjaxResponse, containing a boolean, whether the requested element has a dataset metadata record or not
    """
    element_type = request.GET.get("serviceType")
    if element_type == OGCServiceEnum.WMS.value:
        element = Layer.objects.get(metadata__id=metadata_id)
    elif element_type == OGCServiceEnum.WFS.value:
        element = FeatureType.objects.get(metadata__id=metadata_id)
    else:
        return
    md = element.metadata
    try:
        # the user gave the metadata id of the service metadata, we must resolve this to the related dataset metadata
        md_2 = md.get_related_dataset_metadata()
        doc = Document.objects.get(
            related_metadata=md_2
        )
        has_dataset_doc = doc.dataset_metadata_document is not None
    except ObjectDoesNotExist:
        has_dataset_doc = False

    return BackendAjaxResponse(html="", has_dataset_doc=has_dataset_doc).get_response()


# TODO: currently the preview is not pretty. Refactor this method to get a pretty preview img by consider the right scale of the layers
def get_service_metadata_preview(request: HttpRequest, metadata_id: int):
    """ Returns the service metadata previe als png for a given metadata id

    Args:
        request (HttpRequest): The incoming request
        metadata_id (int): The metadata id
    Returns:
         A HttpResponse containing the png preview
    """
    md = Metadata.objects.get(id=metadata_id)

    if md.service.servicetype.name == OGCServiceEnum.WMS.value and md.service.is_root:
        layer = Layer.objects.get(
            parent_service=Service.objects.get(id=md.service.id),
            parent_layer=None,
        )

    elif md.service.servicetype.name == OGCServiceEnum.WMS.value and not md.service.is_root:
        layer = md.service.layer

    layer = layer.identifier
    bbox = md.find_max_bounding_box()
    bbox = str(bbox.extent).replace("(", "").replace(")", "")  # this is a little dumb, you may choose something better

    # Fetch a supported version of png
    png_format = md.service.get_supported_formats().filter(
        mime_type__icontains="image/"
    ).first()

    data = {
        "request": OGCOperationEnum.GET_MAP.value,
        "version": OGCServiceVersionEnum.V_1_1_1.value,
        "layers": layer,
        "srs": DEFAULT_SRS_STRING,
        "bbox": bbox,
        "format": png_format.mime_type,
        "width": 200,
        "height": 200,
        "service": "wms",
    }

    query_data = QueryDict('', mutable=True)
    query_data.update(data)

    request_post = request.POST
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

    # Make sure the image is returned as PREVIEW_MIME_TYPE_DEFAULT filetype
    image_obj = Image.open(io.BytesIO(response))
    out_bytes_stream = io.BytesIO()
    image_obj.save(out_bytes_stream, PREVIEW_MIME_TYPE_DEFAULT, optimize=True, quality=80)
    response = out_bytes_stream.getvalue()

    return HttpResponse(response, content_type=content_type)


def get_capabilities(request: HttpRequest, metadata_id: int):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        metadata_id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """

    md = Metadata.objects.get(id=metadata_id)
    stored_version = md.get_service_version().value
    # move increasing hits to background process to speed up response time!
    async_increase_hits.delay(metadata_id)

    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    # check that we have the requested version in our database
    version_param = None
    version_tag = None

    request_param = None
    request_tag = None

    use_fallback = None

    for k, v in request.GET.dict().items():
        if k.upper() == "VERSION":
            version_param = v
            version_tag = k
        elif k.upper() == "REQUEST":
            request_param = v
            request_tag = k
        elif k.upper() == "FALLBACK":
            use_fallback = utils.resolve_boolean_attribute_val(v)

    # No version parameter has been provided by the request - we simply use the one we have.
    if version_param is None or len(version_param) == 0:
        version_param = stored_version

    if version_param not in [data.value for data in OGCServiceVersionEnum]:
        # version number not valid
        return HttpResponse(content=PARAMETER_ERROR.format(version_tag), status=404)

    elif request_param is not None and request_param != OGCOperationEnum.GET_CAPABILITIES.value:
        # request not valid
        return HttpResponse(content=PARAMETER_ERROR.format(request_tag), status=404)

    else:
        pass

    if stored_version == version_param or use_fallback is True or not md.is_root():
        # This is the case if
        # 1) a version is requested, which we have in our database
        # 2) the fallback parameter is set explicitly
        # 3) a subelement is requested, which normally do not have capability documents

        # We can check the cache for this document or we need to generate it!
        doc = md.get_current_capability_xml(version_param)
    else:
        # we have to fetch the remote document
        try:
            # fetch the requested capabilities document from remote - we do not provide this as our default (registered) one
            xml = md.get_remote_original_capabilities_document(version_param)

            tmp = xml_helper.parse_xml(xml)
            if tmp is None:
                raise ValueError("No xml document was retrieved. Content was :'{}'".format(xml))

            # we fake the persisted service version, so the document setters will change the correct elements in the xml
            #md.service.servicetype.version = version_param
            doc = Document(
                original_capability_document=xml,
                current_capability_document=xml,
                related_metadata=md
            )
            doc.set_capabilities_secured(auto_save=False)
            if md.use_proxy_uri:
                doc.set_proxy(True, auto_save=False, force_version=version_param)
            doc = doc.current_capability_document
        except (ReadTimeout, TimeoutError, ConnectionError) as e:
            # the remote server does not respond - we must deliver our stored capabilities document, which is not the requested version
            return HttpResponse(content=SERVICE_CAPABILITIES_UNAVAILABLE)

    return HttpResponse(doc, content_type='application/xml')


def get_metadata_html(request: HttpRequest, metadata_id: int):
    """ Returns the metadata as html rendered view
        Args:
            request (HttpRequest): The incoming request
            proxy_log (ProxyLog): The logging object
            id (int): The metadata id
        Returns:
             A HttpResponse containing the html formated metadata
    """
    # ---- constant values
    base_template = '404.html'
    # ----

    md = Metadata.objects.get(id=metadata_id)

    # collect global data for all cases
    params = {
        'md_id': md.id,
        'title': md.title,
        'abstract': md.abstract,
        'access_constraints': md.access_constraints,
        'capabilities_original_uri': md.capabilities_original_uri,
        'capabilities_uri': reverse('service:metadata-proxy-operation', args=(md.id,)) + '?request=GetCapabilities',
        'contact': collect_contact_data(md.contact)
    }

    params.update(collect_metadata_related_objects(md, request,))

    # build the single view cases: wms root, wms layer, wfs root, wfs featuretype, wcs, metadata
    if md.metadata_type.type == MetadataEnum.DATASET.value:
        base_template = 'metadata/base/dataset/dataset_metadata_as_html.html'
        params['contact'] = collect_contact_data(md.contact)
        dataset_doc = Document.objects.get(
            related_metadata=md
        )
        params['dataset_metadata'] = dataset_doc.get_dataset_metadata_as_dict()
        params.update({'capabilities_uri': reverse('service:get-dataset-metadata', args=(md.id,))})

    elif md.metadata_type.type == MetadataEnum.FEATURETYPE.value:
        base_template = 'metadata/base/wfs/featuretype_metadata_as_html.html'
        params.update(collect_featuretype_data(md))

    elif md.metadata_type.type == MetadataEnum.LAYER.value:
        base_template = 'metadata/base/wms/layer_metadata_as_html.html'
        params.update(collect_layer_data(md, request))

    elif md.service.servicetype.name == OGCServiceEnum.WMS.value:
        # wms root object
        base_template = 'metadata/base/wms/root_metadata_as_html.html'
        params.update(collect_wms_root_data(md))

    elif md.service.servicetype.name == OGCServiceEnum.WFS.value:
        # wfs root object
        base_template = 'metadata/base/wfs/root_metadata_as_html.html'
        params.update(collect_wfs_root_data(md, request))

    elif md.service.servicetype.name == OGCServiceEnum.WMC.value:
        base_template = 'metadata/base/wmc/root_metadata_as_html.html'
        # TODO: implement the logic to collect all data
        None

    context = DefaultContext(request, params, None)
    return render(request=request, template_name=base_template, context=context.get_context())


@login_required
def set_session(request: HttpRequest):
    """ Can set a value to the django session

    Args:
        request:
    Returns:
    """
    param_GET = request.GET.dict()
    _session = param_GET.get("session", None)
    if _session is None:
        return BackendAjaxResponse(html="").get_response()
    _session = json.loads(_session)
    for _session_key, _session_val in _session.items():
        request.session[_session_key] = _session_val
    return BackendAjaxResponse(html="").get_response()


@login_required
def wms_index(request: HttpRequest):
    """ Renders an overview of all wms

    Args:t
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    # Default content
    template = "views/wms_index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.get_groups())
    pt_table = PendingTasksTable(pt,
                                 orderable=False, user=user,)

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wms_table(request))

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@login_required
@check_permission(Permission(can_update_service=True))
@transaction.atomic
def update_service(request: HttpRequest, metadata_id: int):
    """ Compare old service with new service and collect differences

    Args:
        request: The incoming request
        metadata_id: The service id
    Returns:
        A rendered view
    """
    template = "views/service_update.html"
    user = user_helper.get_user(request)

    # Check if update check form has been retrieved or an update perform form
    page = int(request.POST.get("page", -1))
    if page == 1:
        # Update check form!
        update_form = UpdateServiceCheckForm(request.POST or None)

        # Check if update form is valid
        if not update_form.is_valid():
            # Form is not valid --> response with page 1 and show errors
            params = {
                "update_service_form": update_form,
                "show_update_form": True,
            }
            return detail(request=request, metadata_id=metadata_id, update_params=params, status_code=422)

        # Get variables from form
        uri = update_form.cleaned_data.get("get_capabilities_uri", None)
        keep_custom_md = update_form.cleaned_data.get("keep_custom_md", None)

        url_dict = service_helper.split_service_uri(uri)
        new_service_type = url_dict.get("service")
        current_service = Service.objects.get(metadata__id=metadata_id)

        # Check cross service update attempt
        if current_service.servicetype.name != new_service_type.value:
            update_form.add_error("get_capabilities_uri", SERVICE_UPDATE_WRONG_TYPE)
            params = {
                "update_service_form": update_form,
                "show_update_form": True,
            }
            return detail(request=request, metadata_id=metadata_id, update_params=params, status_code=422)

        # Create db model from new service information (no persisting, yet)
        registrating_group = current_service.created_by
        new_service = service_helper.get_service_model_instance(
            service_type=url_dict.get("service"),
            version=service_helper.resolve_version_enum(url_dict.get("version")),
            base_uri=url_dict.get("base_uri"),
            user=user,
            register_group=registrating_group
        )
        new_service = new_service["service"]

        # Collect differences
        comparator = ServiceComparator(service_a=new_service, service_b=current_service)
        diff = comparator.compare_services()

        diff_elements = diff.get("layers", None) or diff.get("feature_types", {})
        update_confirmation_form = UpdateOldToNewElementsForm(
            new_elements=diff_elements.get("new"),
            removed_elements=diff_elements.get("removed"),
            keep_custom_md=keep_custom_md,
            get_capabilities_uri=uri
        )
        update_confirmation_form.action_url = reverse("service:update", args=[metadata_id])

        params = {
            "current_service": current_service,
            "update_service": new_service,
            "diff_elements": diff_elements,
            "update_confirmation_form": update_confirmation_form,
        }
        context = DefaultContext(request, params, user)
        return render(request=request, template_name=template, context=context.get_context(), status=202)

    elif page == 2:
        # Update perform form!
        # We need to extract the linkage of new->old elements from the request by hand
        links = {}
        prefix = "new_elem_"
        for key, val in request.POST.items():
            if prefix in key:
                links[key.replace(prefix, "")] = int(val)

        uri = request.POST.get("capabilities_url", None)
        keep_custom_md = utils.resolve_boolean_attribute_val(request.POST.get("keep_custom_md", True))

        if uri is None:
            messages.error(request, PARAMETER_ERROR.format("Get capabilities uri"))
            return HttpResponseRedirect(reverse("service:detail", args=(metadata_id,)), status=303)

        url_dict = service_helper.split_service_uri(uri)
        current_service = Service.objects.get(metadata__id=metadata_id)

        # Create db model from new service information (no persisting, yet)
        registrating_group = current_service.created_by
        new_service = service_helper.get_service_model_instance(
            service_type=url_dict.get("service"),
            version=service_helper.resolve_version_enum(url_dict.get("version")),
            base_uri=url_dict.get("base_uri"),
            user=user,
            register_group=registrating_group
        )
        new_service_capabilities_xml = new_service["raw_data"].service_capabilities_xml
        new_service = new_service["service"]

        # Collect differences
        comparator = ServiceComparator(service_a=new_service, service_b=current_service)
        diff = comparator.compare_services()

        # UPDATE
        # First update the metadata of the whole service
        md = update_helper.update_metadata(current_service.metadata, new_service.metadata, keep_custom_md)
        md.save()
        current_service.metadata = md

        # Then update the service object
        current_service = update_helper.update_service(current_service, new_service)

        # Update the subelements
        if new_service.servicetype.name == OGCServiceEnum.WFS.value:
            current_service = update_helper.update_wfs_elements(
                current_service,
                new_service,
                diff,
                links,
                keep_custom_md
            )
        elif new_service.servicetype.name == OGCServiceEnum.WMS.value:
            current_service = update_helper.update_wms_elements(
                current_service,
                new_service,
                diff,
                links,
                keep_custom_md
            )

        update_helper.update_capability_document(current_service, new_service_capabilities_xml)

        current_service.save()
        user_helper.create_group_activity(
            current_service.metadata.created_by,
            user,
            SERVICE_UPDATED,
            current_service.metadata.title
        )

        messages.success(request, SERVICE_UPDATED)
        return HttpResponseRedirect(reverse("service:detail", args=(metadata_id,)), status=303)


@login_required
def wfs_index(request: HttpRequest):
    """ Renders an overview of all wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    user = user_helper.get_user(request)

    # Default content
    template = "views/wfs_index.html"

    # get pending tasks
    pending_tasks = PendingTask.objects.filter(created_by__in=user.get_groups())
    pt_table = PendingTasksTable(pending_tasks,
                                 orderable=False, user=user,)

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wfs_table(request))

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@login_required
def detail(request: HttpRequest, metadata_id: int, update_params=None, status_code=None):
    """ Renders a detail view of the selected service

    Args:
        request: The incoming request
        metadata_id: The id of the selected metadata
        update_params: dict with params we will update before we return the context
        status_code
    Returns:
    """
    user = user_helper.get_user(request)

    template = "views/detail.html"
    service_md = get_object_or_404(Metadata, id=metadata_id)
    params = {}

    # catch featuretype
    if service_md.metadata_type.type == 'featuretype':
        params.update({'caption': _("Shows informations about the featuretype which you are selected.")})
        template = "views/featuretype_detail_no_base.html" if 'no-base' in request.GET else "views/featuretype_detail.html"
        service = service_md.featuretype
        layers_md_list = {}
    else:
        if service_md.service.is_root:
            params.update({'caption': _("Shows informations about the service which you are selected.")})
            service = service_md.service
            layers = Layer.objects.filter(parent_service=service_md.service)
            layers_md_list = layers.filter(parent_layer=None)
        else:
            params.update({'caption': _("Shows informations about the sublayer which you are selected.")})
            template = "views/sublayer_detail_no_base.html" if 'no-base' in request.GET else "views/sublayer_detail.html"
            service = Layer.objects.get(
                metadata=service_md
            )
            # get sublayers
            layers_md_list = Layer.objects.filter(
                parent_layer=service_md.service
            )

    try:
        related_md = MetadataRelation.objects.get(
            metadata_from=service_md,
            metadata_to__metadata_type__type='dataset',
        )
        document = Document.objects.get(
            related_metadata=related_md.metadata_to
        )
        has_dataset_metadata = document.dataset_metadata_document is not None
    except ObjectDoesNotExist:
        has_dataset_metadata = False

    mime_types = {}
    for mime in service.formats.all():
        op = mime_types.get(mime.operation)
        if op is None:
            op = []
        op.append(mime.mime_type)
        mi = {mime.operation: op}
        mime_types.update(mi)

    remove_service_form = RemoveServiceForm(
        initial={
            'service_id': service.id,
            'service_needs_authentication': False,
        }
    )
    remove_service_form.action_url = reverse('service:remove', args=[metadata_id])

    update_service_check_form = UpdateServiceCheckForm(
        initial={
            'service_id': service.id,
            'service_needs_authentication': False,
        }
    )
    update_service_check_form.action_url = reverse('service:update', args=[metadata_id])

    params.update({
        "has_dataset_metadata": has_dataset_metadata,
        "service_md": service_md,
        "service": service,
        "layers": layers_md_list,
        "mime_types": mime_types,
        "update_service_form": update_service_check_form,
        "remove_service_form": remove_service_form,
        "leaflet_add_bbox": True,
    })

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request,
                  template_name=template,
                  context=context.get_context(),
                  status=200 if status_code is None else status_code)


@csrf_exempt
@log_proxy
def get_operation_result(request: HttpRequest, proxy_log: ProxyLog, metadata_id: int):
    """ Checks whether the requested metadata is secured and resolves the operations uri for an allowed user - or not.

    Decides which operation will be handled by resolving a given 'request=' query parameter.
    This function has to be public available (no check_session decorator)
    The decorator allows POST requests without CSRF tokens (for non logged in users)

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        id (int): The metadata id
        user (MrMapUser): The performing user
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
            return get_capabilities(request=request, metadata_id=metadata_id)

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
            md_secured = True in [l_md.is_secured for l_md in layers_md]

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
            proxy_log.log_response(response, operation_handler.request_param)

        len_response = len(response)

        if len_response <= 50000:
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


def get_metadata_legend(request: HttpRequest, metadata_id: int, style_id: int):
    """ Calls the legend uri of a special style inside the metadata (<LegendURL> element) and returns the response to the user

    This function has to be public available (no check_session decorator)

    Args:
        request (HttpRequest): The incoming HttpRequest
        metadata_id (int): The metadata id
        style_id (int): The style id
    Returns:
        HttpResponse
    """
    uri = Style.objects.get(id=style_id).legend_uri
    con = CommonConnector(uri)
    con.load()
    response = con.content
    return HttpResponse(response, content_type="")
