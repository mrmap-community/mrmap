import io
import json
from io import BytesIO
from PIL import Image
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, QueryDict
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django_tables2 import RequestConfig
from requests import ReadTimeout
from MapSkinner import utils
from MapSkinner.cacher import PreviewImageCacher
from MapSkinner.consts import *
from MapSkinner.decorator import check_session, check_permission, log_proxy
from MapSkinner.messages import FORM_INPUT_INVALID, SERVICE_UPDATE_WRONG_TYPE, \
    SERVICE_REMOVED, SERVICE_UPDATED, \
    SERVICE_NOT_FOUND, SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE, SERVICE_DISABLED, SERVICE_LAYER_NOT_FOUND, \
    SECURITY_PROXY_NOT_ALLOWED, CONNECTION_TIMEOUT, PARAMETER_ERROR, SERVICE_CAPABILITIES_UNAVAILABLE
from MapSkinner.responses import BackendAjaxResponse, DefaultContext
from MapSkinner.settings import ROOT_URL, PAGE_SIZE_DEFAULT, PAGE_DEFAULT
from service import tasks
from service.helper import xml_helper
from service.filters import WmsFilter, WfsFilter
from service.forms import ServiceURIForm, RegisterNewServiceWizardPage1, \
    RegisterNewServiceWizardPage2, RemoveService
from service.helper import service_helper, update_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCOperationEnum, OGCServiceVersionEnum, MetadataEnum
from service.helper.ogc.operation_request_handler import OGCOperationRequestHandler
from service.helper.service_comparator import ServiceComparator
from service.settings import DEFAULT_SRS_STRING, PREVIEW_MIME_TYPE_DEFAULT
from service.tables import WmsServiceTable, WmsLayerTable, WfsServiceTable, PendingTasksTable
from service.tasks import async_increase_hits
from service.models import Metadata, Layer, Service, FeatureType, Document, MetadataRelation, Style, ProxyLog
from service.tasks import async_remove_service_task
from service.utils import collect_contact_data, collect_metadata_related_objects, collect_featuretype_data, \
    collect_layer_data, collect_wms_root_data, collect_wfs_root_data
from structure.models import User, Permission, PendingTask, Group
from users.helper import user_helper
from django.urls import reverse
from django import forms


def _prepare_wms_table(request: HttpRequest, user: User, ):
    """ Collects all wms service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (User): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    # whether whole services or single layers should be displayed

    if 'show_layers' in request.GET and request.GET.get("show_layers").lower() == 'on':
        show_service = False
    else:
        show_service = True

    md_list_wms = Metadata.objects.filter(
        service__servicetype__name=OGCServiceEnum.WMS.value,
        service__is_root=show_service,
        created_by__in=user.groups.all(),
        is_deleted=False,
    ).order_by("title")

    wms_table_filtered = WmsFilter(request.GET, queryset=md_list_wms)

    if show_service:
        wms_table = WmsServiceTable(wms_table_filtered.qs,
                                    template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                    order_by_field='swms',  # swms = sort wms
                                    user=user,)
    else:
        wms_table = WmsLayerTable(wms_table_filtered.qs,
                                  template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
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


def _prepare_wfs_table(request: HttpRequest, user: User, ):
    """ Collects all wfs service data and prepares parameter for rendering

    Args:
        request (HttpRequest): The incoming request
        user (User): The performing user
    Returns:
         params (dict): The rendering parameter
    """
    md_list_wfs = Metadata.objects.filter(
        service__servicetype__name=OGCServiceEnum.WFS.value,
        created_by__in=user.groups.all(),
        is_deleted=False,
    ).order_by("title")

    wfs_table_filtered = WfsFilter(request.GET, queryset=md_list_wfs)
    wfs_table = WfsServiceTable(wfs_table_filtered.qs,
                                template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                order_by_field='swfs',  # swms = sort wms
                                user=user,)

    wfs_table.filter = wfs_table_filtered
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    wfs_table.configure_pagination(request, 'wfs-t')

    params = {
        "wfs_table": wfs_table,
    }

    return params


def _new_service_wizard_page1(request: HttpRequest, user: User,):
    # Page One is posted --> validate it
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
                                                              selected_group=user.groups.first()),
            "show_modal": True,
        }
    else:
        # Form is not valid --> response with page 1 and show errors
        params = {
            "new_service_form": form,
            "show_modal": True,
        }
    return index(request=request, update_params=params)


def _new_service_wizard_page2(request: HttpRequest, user: User,):
    # Page two is posted --> collect all data from post and initial the form
    selected_group = user.groups.all().get(id=int(request.POST.get("registering_with_group")))

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
    form = RegisterNewServiceWizardPage2(request.POST,
                                         initial=init_data,
                                         user=user,
                                         selected_group=selected_group,
                                         service_needs_authentication=is_auth_needed,
                                         )

    # first check if it's just a update of the form
    if request.POST.get("is_form_update") == 'True':
        # it's just a updated form state. return the new state as view
        params = {
            "new_service_form": form,
            "show_modal": True,
        }
    else:
        # it's not a update. we have to validate the fields now
        # and if all is fine generate a new pending task object
        form = RegisterNewServiceWizardPage2(request.POST,
                                             initial=init_data,
                                             user=user,
                                             selected_group=selected_group,
                                             service_needs_authentication=is_auth_needed)

        if form.is_valid():
            # run creation async!
            external_auth = None
            if form.cleaned_data['service_needs_authentication']:
                external_auth = {
                    "username": form.cleaned_data['username'],
                    "password": form.cleaned_data['password'],
                    "auth_type": form.cleaned_data['authentication_type']
                }

            register_for_other_org = 'None'
            if form.cleaned_data['registering_for_other_organization'] is not None:
                register_for_other_org = form.cleaned_data['registering_for_other_organization'].id

            uri_dict = {
                "base_uri": form.cleaned_data["uri"],
                "version": form.cleaned_data["ogc_version"],
                "service": form.cleaned_data["ogc_service"],
                "request": form.cleaned_data["ogc_request"],
            }

            try:
                pending_task = tasks.async_new_service.delay(
                    uri_dict,
                    user.id,
                    form.cleaned_data['registering_with_group'].id,
                    register_for_other_org,
                    external_auth
                )

                # create db object, so we know which pending task is still ongoing
                pending_task_db = PendingTask()
                pending_task_db.created_by = Group.objects.get(
                    id=form.cleaned_data['registering_with_group'].id)
                pending_task_db.task_id = pending_task.task_id
                pending_task_db.description = json.dumps({
                    "service": form.cleaned_data['uri'],
                    "phase": "Parsing",
                })

                pending_task_db.save()

                # everthing works well. Redirect to index page.
                return redirect(SERVICE_INDEX)

            except Exception as e:
                # Form is not valid --> response with page 2 and show errors
                form.add_error(None, e)
                params = {
                    "new_service_form": form,
                    "show_modal": True,
                }
        else:
            # Form is not valid --> response with page 2 and show errors
            params = {
                "new_service_form": form,
                "show_modal": True,
            }

    return index(request=request, update_params=params)


@check_session
def add(request: HttpRequest, user: User):
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
            return _new_service_wizard_page1(request, user)
        if page == 2:
            return _new_service_wizard_page2(request, user)

    return redirect(SERVICE_INDEX)


@check_session
def index(request: HttpRequest, user: User, update_params=None):
    """ Renders an overview of all wms and wfs

    Args:
        request (HttpRequest): The incoming request
        user (User): The session user
        update_params: (Optional) the update_params dict
    Returns:
         A view
    """
    # Default content
    template = "views/index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.groups.all())
    pt_table = PendingTasksTable(pt,
                                 template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                 orderable=False, user=user, )

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wms_table(request, user, ))
    params.update(_prepare_wfs_table(request, user, ))

    if update_params:
        params.update(update_params)

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def pending_tasks(request: HttpRequest, user: User):
    """ Renders a table of all pending tasks

    Args:
        request (HttpRequest): The incoming request
        user (User): The session user
    Returns:
         A view
    """
    # Default content
    template = "includes/pending_tasks.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.groups.all())

    pt_table = PendingTasksTable(pt,
                                 template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                 orderable=False, user=user,)

    params = {
        "pt_table": pt_table,
        "user": user,
    }

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
@check_permission(Permission(can_remove_service=True))
def remove(request: HttpRequest, id:int, user: User):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
        user (User): The performing user
    Returns:
        Redirect to service:index
    """

    remove_form = RemoveService(request.POST)
    if remove_form.is_valid():
        metadata = get_object_or_404(Metadata, id=id)
        service_type = metadata.get_service_type()
        sub_elements = None

        if service_type == OGCServiceEnum.WMS.value:
            sub_elements = Layer.objects.filter(parent_service__metadata=metadata)
        elif service_type == OGCServiceEnum.WFS.value:
            sub_elements = FeatureType.objects.filter(parent_service__metadata=metadata)

        if remove_form.cleaned_data['is_confirmed']:
            # remove service and all of the related content
            user_helper.create_group_activity(metadata.created_by, user, SERVICE_REMOVED, metadata.title)

            # set service as deleted, so it won't be listed anymore in the index view until completely removed
            metadata.is_deleted = True
            metadata.save()

            # TODO: we dont know this at this time; refactor this; async_remove function should add messages
            messages.success(request, 'Service "{}" successfully deleted.'.format(metadata.title))

            # call removing as async task
            async_remove_service_task.delay(metadata.service.id)

            return redirect(SERVICE_INDEX)
        else:
            # TODO: redirect to service:detail; show modal by default with error message
            params = {
                "service": metadata,
                "metadata": metadata,
                "sub_elements": sub_elements,
            }
            return redirect("service:detail", id)
    else:
        # TODO: redirect to service:detail; show modal by default with error message
        return redirect("service:detail", id)


# TODO: update function documentation
@check_session
@check_permission(Permission(can_activate_service=True))
def activate(request: HttpRequest, id: int, user: User):
    """ (De-)Activates a service and all of its layers

    Args:
        user:
        id:
        request:
    Returns:
         An Ajax response
    """
    # run activation async!
    tasks.async_activate_service.delay(id, user.id)

    # TODO: we dont know this at this time; refactor this; async_remove function should add messages
    messages.success(request, 'Service %s successfully (de-)activated.' % id)

    return redirect("service:index")


@log_proxy
def get_service_metadata(request: HttpRequest, proxy_log: ProxyLog, id: int):
    """ Returns the service metadata xml file for a given metadata id

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    metadata = Metadata.objects.get(id=id)

    if not metadata.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    doc = metadata.get_service_metadata_xml()

    return HttpResponse(doc, content_type=APP_XML)


def get_dataset_metadata(request: HttpRequest, id: int):
    """ Returns the dataset metadata xml file for a given metadata id

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    md = Metadata.objects.get(id=id)
    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)
    try:
        if md.metadata_type.type != OGCServiceEnum.DATASET.value:
            # the user gave the metadata id of the service metadata, we must resolve this to the related dataset metadata
            md = md.get_related_dataset_metadata()
            if md is None:
                raise ObjectDoesNotExist
            return redirect("service:get-dataset-metadata", id=md.id)
        document = Document.objects.get(related_metadata=md)
        document = document.dataset_metadata_document
        if document is None:
            raise ObjectDoesNotExist
    except ObjectDoesNotExist:
        return HttpResponse(content=_("No dataset metadata found"), status=404)
    return HttpResponse(document, content_type='application/xml')


def check_for_dataset_metadata(request: HttpRequest, id: int):
    """ Checks whether an element (layer or featuretype) has a dataset metadata record.

    This function is used for ajax calls from the client, to check dynamically on an opened subelement if there
    are dataset metadata to get.

    Args:
        request (HttpRequest): The incoming request
        id (int): The element id
    Returns:
         A BackendAjaxResponse, containing a boolean, whether the requested element has a dataset metadata record or not
    """
    element_type = request.GET.get("serviceType")
    if element_type == OGCServiceEnum.WMS.value:
        element = Layer.objects.get(metadata__id=id)
    elif element_type == OGCServiceEnum.WFS.value:
        element = FeatureType.objects.get(metadata__id=id)
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


@log_proxy
# TODO: currently the preview is not pretty. Refactor this method to get a pretty preview img by consider the right scale of the layers
def get_service_metadata_preview(request: HttpRequest, proxy_log: ProxyLog, id: int):
    """ Returns the service metadata previe als png for a given metadata id

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        id (int): The metadata id
    Returns:
         A HttpResponse containing the png preview
    """
    md = Metadata.objects.get(id=id)

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


def get_capabilities(request: HttpRequest, id: int):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """

    md = Metadata.objects.get(id=id)
    stored_version = md.get_service_version().value
    # move increasing hits to background process to speed up response time!
    async_increase_hits.delay(id)

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


@log_proxy
def get_metadata_html(request: HttpRequest, proxy_log: ProxyLog, id: int):
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

    md = Metadata.objects.get(id=id)

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


@log_proxy
def get_capabilities_original(request: HttpRequest, proxy_log: ProxyLog, id: int):
    """ Returns the current capabilities xml file

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        id (int): The metadata id
    Returns:
         A HttpResponse containing the xml file
    """
    md = Metadata.objects.get(id=id)

    if not md.is_active:
        return HttpResponse(content=SERVICE_DISABLED, status=423)

    # move increasing hits to background process to speed up response time!
    async_increase_hits.delay(id)
    cap_doc = Document.objects.get(related_metadata=md)
    doc = cap_doc.original_capability_document

    return HttpResponse(doc, content_type='application/xml')


@check_session
def set_session(request: HttpRequest, user: User):
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


@check_session
def wms_index(request: HttpRequest, user: User):
    """ Renders an overview of all wms

    Args:t
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    # Default content
    template = "views/wms_index.html"

    # get pending tasks
    pt = PendingTask.objects.filter(created_by__in=user.groups.all())
    pt_table = PendingTasksTable(pt,
                                 template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                 orderable=False, user=user,)

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wms_table(request, user, ))

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


# TODO: refactor this function and template by using bootstrap4
@check_session
@check_permission(Permission(can_update_service=True))
@transaction.atomic
def update_service(request: HttpRequest, user: User, id: int):
    """ Compare old service with new service and collect differences

    Args:
        request: The incoming request
        user: The active user
        id: The service id
    Returns:
        A rendered view
    """
    template = "service_differences.html"
    update_params = request.session["update"]
    url_dict = service_helper.split_service_uri(update_params["full_uri"])
    new_service_type = url_dict.get("service")
    old_service = Service.objects.get(id=id)

    # check if metadata should be kept
    keep_custom_metadata = request.POST.get("keep-metadata", None)
    if keep_custom_metadata is None:
        keep_custom_metadata = request.session.get("keep-metadata", "")
    request.session["keep-metadata"] = keep_custom_metadata
    keep_custom_metadata = keep_custom_metadata == "on"

    # get info which layers/featuretypes are linked (old->new)
    links = json.loads(request.POST.get("storage", '{}'))
    update_confirmed = utils.resolve_boolean_attribute_val(request.POST.get("confirmed", 'false'))

    # parse new capabilities into db model
    registrating_group = old_service.created_by
    new_service = service_helper.get_service_model_instance(service_type=url_dict.get("service"),
                                                            version=url_dict.get("version"),
                                                            base_uri=url_dict.get("base_uri"), user=user,
                                                            register_group=registrating_group)
    xml = new_service["raw_data"].service_capabilities_xml
    new_service = new_service["service"]

    # Collect differences
    comparator = ServiceComparator(service_1=new_service, service_2=old_service)
    diff = comparator.compare_services()

    if update_confirmed:
        # check cross service update attempt
        if old_service.servicetype.name != new_service_type.value:
            # cross update attempt -> forbidden!
            messages.add_message(request, messages.ERROR, SERVICE_UPDATE_WRONG_TYPE)
            return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(
                old_service.metadata.id))).get_response()
        # check if new capabilities is even different from existing
        # if not we do not need to spend time and money on performing it!
        # if not service_helper.capabilities_are_different(update_params["full_uri"], old_service.metadata.capabilities_original_uri):
        #     messages.add_message(request, messages.INFO, SERVICE_UPDATE_ABORTED_NO_DIFF)
        #     return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(old_service.metadata.id))).get_response()

        if not keep_custom_metadata:
            # the update is confirmed, we can continue changing the service!
            # first update the metadata of the whole service
            md = update_helper.update_metadata(old_service.metadata, new_service.metadata)
            old_service.metadata = md
            # don't forget the timestamp when we updated the last time
            old_service.metadata.last_modified = timezone.now()
            # save the metadata changes
            old_service.metadata.save()
        # secondly update the service itself, overwrite the metadata with the previously updated metadata
        old_service = update_helper.update_service(old_service, new_service)
        old_service.last_modified = timezone.now()

        if new_service.servicetype.name == OGCServiceEnum.WFS.value:
            old_service = update_helper.update_wfs(old_service, new_service, diff, links, keep_custom_metadata)

        elif new_service.servicetype.name == OGCServiceEnum.WMS.value:
            old_service = update_helper.update_wms(old_service, new_service, diff, links, keep_custom_metadata)

        cap_document = Document.objects.get(related_metadata=old_service.metadata)
        cap_document.current_capability_document = xml
        cap_document.save()

        old_service.save()
        del request.session["keep-metadata"]
        del request.session["update"]
        user_helper.create_group_activity(old_service.metadata.created_by, user, SERVICE_UPDATED,
                                          old_service.metadata.title)
        return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(
            old_service.metadata.id))).get_response()
    else:
        # otherwise
        params = {
            "diff": diff,
            "old_service": old_service,
            "new_service": new_service,
            "page_indicator_list": [False, True],
        }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


@check_session
def discard_update(request: HttpRequest, user: User):
    """ If the user does not want to proceed with the update,
    we need to go back and drop the session stored data about the update

    Args:
        request (HttpRequest):
        user (User):
    Returns:
         redirects
    """
    del request.session["update"]
    return redirect("service:index")


@check_session
@check_permission(Permission(can_update_service=True))
def update_service_form(request: HttpRequest, user: User, id: int):
    """ Creates the form for updating a service

    Args:
        request: The incoming request
        user: The current user
        id: The service id
    Returns:
         A BackendAjaxResponse
    """
    template = "overlay/service_url_form.html"
    uri_form = ServiceURIForm(request.POST or None)
    params = {}
    if request.method == 'POST':
        template = "overlay/update_service.html"
        if uri_form.is_valid():
            error = False
            cap_url = uri_form.data.get("uri", "")
            url_dict = service_helper.split_service_uri(cap_url)

            if url_dict["request"] != "GetCapabilities":
                # not allowed!
                error = True

            try:
                # get current service to compare with
                service = Service.objects.get(id=id)
                params = {
                    "action_url": ROOT_URL + "/service/update/" + str(id),
                    "service": service,
                    "error": error,
                    "uri": url_dict["base_uri"],
                    "version": url_dict["version"].value,
                    "service_type": url_dict["service"].value,
                    "request_action": url_dict["request"],
                    "full_uri": cap_url,
                    "page_indicator_list": [False, True],
                }
                request.session["update"] = {
                    "full_uri": cap_url,
                }
            except AttributeError:
                params = {
                    "error": error,
                    "page_indicator_list": [False, True],
                }

        else:
            params = {
                "error": FORM_INPUT_INVALID,
                "page_indicator_list": [False, True],
            }

    else:
        params = {
            "form": uri_form,
            "article": _("Enter the new capabilities URL of your service."),
            "action_url": ROOT_URL + "/service/register-form/" + str(id),
            "button_text": "Update",
            "page_indicator_list": [True, False],
        }
    params["service_id"] = id
    html = render_to_string(template_name=template, request=request, context=params)
    return BackendAjaxResponse(html=html).get_response()


#TODO: refactor this method
@check_session
def wfs_index(request: HttpRequest, user: User):
    """ Renders an overview of all wfs

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A view
    """
    # Default content
    template = "views/wfs_index.html"

    # get pending tasks
    pending_tasks = PendingTask.objects.filter(created_by__in=user.groups.all())
    pt_table = PendingTasksTable(pending_tasks,
                                 template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE,
                                 orderable=False, user=user,)

    params = {
        "pt_table": pt_table,
        "new_service_form": RegisterNewServiceWizardPage1(),
        "user": user,
    }

    params.update(_prepare_wfs_table(request, user, ))

    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def detail(request: HttpRequest, id, user: User):
    """ Renders a detail view of the selected service

    Args:
        request: The incoming request
        id: The id of the selected metadata
    Returns:
    """
    template = "views/detail.html"
    service_md = get_object_or_404(Metadata, id=id)
    params = {}

    # catch featuretype
    if service_md.metadata_type.type == 'featuretype':
        params.update({'caption': _("Shows informations about the featuretype which you are selected.")})
        if 'no-base' in request.GET:
            template = "views/featuretype_detail_no_base.html"
        else:
            template = "views/featuretype_detail.html"
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
            if 'no-base' in request.GET:
                template = "views/sublayer_detail_no_base.html"
            else:
                template = "views/sublayer_detail.html"
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

    remove_service_form = RemoveService(initial={'service_id': service.id,
                                                 'service_needs_authentication': False,
                                                 })
    remove_service_form.action_url = reverse('service:remove', args=[id])

    params.update({
        "has_dataset_metadata": has_dataset_metadata,
        "service_md": service_md,
        "service": service,
        "layers": layers_md_list,
        "mime_types": mime_types,
        "remove_service_form": remove_service_form,
        "leaflet_add_bbox": True,
    })
    context = DefaultContext(request, params, user)
    return render(request=request, template_name=template, context=context.get_context())


@check_session
def detail_child(request: HttpRequest, id, user: User):
    """ Returns a rendered html overview of the element with the given id

    Args:
        request (HttpRequest): The incoming request
        id (int): The element id
        user (User): The performing user
    Returns:
         A rendered view for ajax insertion
    """
    element_type = request.GET.get("serviceType")
    if element_type == "wms":
        template = "detail/service_detail_child_wms.html"
        element = Layer.objects.get(id=id)
    elif element_type == "wfs":
        template = "detail/service_detail_child_wfs.html"
        element = FeatureType.objects.get(id=id)
    else:
        template = ""
        element = None

    params = {
        "element": element,
        "user_permissions": user.get_permissions(),
    }
    html = render_to_string(template_name=template, context=params)
    return BackendAjaxResponse(html=html).get_response()


def metadata_proxy(request: HttpRequest, id: int):
    """ Returns the xml document which is resolved by the metadata id.

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         HttpResponse
    """
    md = Metadata.objects.get(id=id)
    con = CommonConnector(url=md.metadata_url)
    con.load()
    xml_raw = con.content
    return HttpResponse(xml_raw, content_type='application/xml')


@csrf_exempt
@log_proxy
def get_operation_result(request: HttpRequest, proxy_log: ProxyLog, id: int):
    """ Checks whether the requested metadata is secured and resolves the operations uri for an allowed user - or not.

    Decides which operation will be handled by resolving a given 'request=' query parameter.
    This function has to be public available (no check_session decorator)
    The decorator allows POST requests without CSRF tokens (for non logged in users)

    Args:
        request (HttpRequest): The incoming request
        proxy_log (ProxyLog): The logging object
        id (int): The metadata id
        user (User): The performing user
    Returns:
         A redirect to the GetMap uri
    """
    # get request type and requested layer
    get_query_string = request.environ.get("QUERY_STRING", "")

    try:
        # redirects request to parent service, if the given id is not the root of the service
        metadata = Metadata.objects.get(id=id)
        operation_handler = OGCOperationRequestHandler(uri=get_query_string, request=request, metadata=metadata)

        if not metadata.is_active:
            return HttpResponse(status=423, content=SERVICE_DISABLED)

        elif operation_handler.request_param is None:
            return HttpResponse(status=500, content=SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE)

        elif operation_handler.request_param.upper() == OGCOperationEnum.GET_CAPABILITIES.value.upper():
            return get_capabilities(request=request, id=id)

        elif not metadata.is_root():
            # we do not allow the direct call of operations on child elements, such as layers!
            # if the request tries that, we directly redirect it to the parent service!
            parent_md = metadata.service.parent_service.metadata
            return get_operation_result(request=request, id=parent_md.id)

        # We need to check if one of the requested layers is secured. If so, we need to check the
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
            proxy_log.log_response(response)

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


def get_metadata_legend(request: HttpRequest, id: int, style_id: id):
    """ Calls the legend uri of a special style inside the metadata (<LegendURL> element) and returns the response to the user

    This function has to be public available (no check_session decorator)

    Args:
        request (HttpRequest): The incoming HttpRequest
        id (int): The metadata id
        style_id (int): The stlye id
        user (User): The performing user
    Returns:
        HttpResponse
    """
    uri = Style.objects.get(id=style_id).legend_uri
    con = CommonConnector(uri)
    con.load()
    response = con.content
    return HttpResponse(response, content_type="")
