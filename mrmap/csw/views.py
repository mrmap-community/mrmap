
from django.db.models.expressions import F
from django.db.models.fields import CharField
from django.db.models.functions import Concat, datetime
from django.db.models.query_utils import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from ows_lib.models.ogc_request import OGCRequest
from registry.models.metadata import MetadataRelation
from registry.proxy.ogc_exceptions import (MissingRequestParameterException,
                                           MissingServiceParameterException,
                                           MissingVersionParameterException,
                                           OperationNotSupportedException)


@method_decorator(csrf_exempt, name="dispatch")
class CswServiceView(View):
    """
    MrMap CSW implementation

    """

    def dispatch(self, request, *args, **kwargs):
        print("huhu")
        self.start_time = datetime.datetime.now()
        self.ogc_request = OGCRequest.from_django_request(request)

        exception = self.check_request()
        if exception:
            return exception
        # self.analyze_request()

        return self.get_and_post(request=request, *args, **kwargs)

    def check_request(self):
        """proof if all mandatory query parameters are part of the reuqest"""
        if not self.ogc_request.operation:
            return MissingRequestParameterException(ogc_request=self.ogc_request)
        elif not self.ogc_request.service_type:
            return MissingServiceParameterException(ogc_request=self.ogc_request)

    def get_capabilities(self):
        """Return the camouflaged capabilities document of the founded service.
        .. note::
           See :meth:`registry.models.document.DocumentModelMixin.xml_secured` for details of xml_secured function.
        :return: the camouflaged capabilities document.
        :rtype: :class:`django.http.response.HttpResponse`
        """
        # TODO: build capabilities document for mrmap csw server
        content = ""

        return HttpResponse(
            status=200, content=content, content_type="application/xml"
        )

    def get_records(self, request):

        # this dict mapps the ogc specificated filterable attributes to our database schema(s)
        field_mapping = {
            "title": "title",
            "dc:title": "title",
            "abstract": "abstract",
            "dc:abstract": "abstract",
            "description": "abstract",
            "subject": "keywords",  # TODO: keywords right?
            "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record
            "coverage": "bounding_geometry",
            "ows:BoundingBox": "bounding_geometry",
            "date": "date_stamp",
            "dc:modified": "date_stamp",
            "type": "type",
            "dc:type": "type",
            "ResourceIdentifier": "resource_identifier"
        }
        q = self.ogc_request.filter_constraint(field_mapping=field_mapping)

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self

        result = MetadataRelation.objects.annotate(
            resource_identifier=Concat(F("dataset_metadata__dataset_id_code_space"), F(
                "dataset_metadata__dataset_id"),  output_field=CharField())
        )

        # TODO: catch FieldError for unsupported filter fields
        result = result.filter(q)

        result_type = self.ogc_request.ogc_query_params.get(
            "resultType", "hits")

        if result_type == "hits":
            result = result.count()

    def get_and_post(self, request, *args, **kwargs):
        """Http get/post method

        :return:
        :rtype: dict or :class:`requests.models.Request`
        """
        if self.ogc_request.is_get_capabilities_request:
            return self.get_capabilities()
        elif self.ogc_request.is_get_records_request:
            return self.get_records(request=request)
        # TODO: other csw operations
        else:

            return OperationNotSupportedException(ogc_request=self.ogc_request)
