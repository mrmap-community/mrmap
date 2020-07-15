"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
import json

import requests
from lxml.etree import Element

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper
from service.helper.enums import OGCOperationEnum
from service.models import Metadata
from structure.models import PendingTask


class Harvester:
    def __init__(self, metadata: Metadata):
        self.metadata = metadata
        self.harvest_url = metadata.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_RECORDS.value,
        ).exclude(
            url=None
        ).first()

        self.version = self.metadata.get_service_version().value
        self.max_records_per_request = 500
        self.start_position = 1

        self.method = self.harvest_url.method

        self.harvest_url = getattr(self.harvest_url, "url", None)
        if self.harvest_url is None:
            raise ValueError("NO GET RECORDS URL AVAILABLE")
        self.output_format = getattr(
            self.metadata.formats.filter(
                mime_type__icontains="xml"
            ).first(),
            "mime_type",
            None
        )

        if self.output_format is None:
            raise ValueError("NO XML OUTPUT FORMAT AVAILABLE")

        self.pending_task = None  # will be initialized in harvest()

    def _generate_request_POST_body(self, start_position: int, result_type: str = "results"):
        """ Creates a CSW POST body xml document for GetRecords

        Args:
            start_position (int): The start position for the request
        Returns:
             xml (str): The GetRecords xml document
        """
        namespaces = {
            "apiso": "http://www.opengis.net/cat/csw/apiso/1.0",
            "ogc": "http://www.opengis.net/ogc",
            "gmd": "http://www.isotc211.org/2005/gmd",
            "ows": "http://www.opengis.net/ows",
            "xsd": "http://www.w3.org/2001/XMLSchema",
            "xsi": "http://www.w3.org/2001/XMLSchema",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dct": "http://purl.org/dc/terms/",
            "schemaLocation": "http://www.opengis.net/cat/csw/{}".format(self.version),
            None: "http://www.opengis.net/cat/csw/{}".format(self.version),
        }

        root_elem = Element(
            OGCOperationEnum.GET_RECORDS.value,
            attrib={
                "version": self.version,
                "service": "CSW",
                "resultType": result_type,
                "outputFormat": self.output_format,
                "startPosition": str(start_position),
                "maxRecords": str(self.max_records_per_request),
                #"{}schemaLocation".format(xsi_ns): "http://www.opengis.net/cat/csw/2.0.2",
            },
            nsmap=namespaces
        )
        xml_helper.create_subelement(
            root_elem,
            "Query",
            None,
            {
                "typeNames": "gmd:MD_Metadata"
            }
        )

        return xml_helper.xml_to_string(root_elem)

    def harvest(self):
        """ Starts harvesting procedure

        Returns:

        """
        # Create a pending task record for the database first!
        self.pending_task = PendingTask.objects.get_or_create(
            task_id=self.metadata.public_id,
            description=json.dumps({
                "service": self.metadata.title,
                "phase": "Parsing",
            }),
            progress=0,
        )[0]

        # Perform the initial "hits" request to get an overview of how many data will be fetched
        hits_response = self._get_harvest_response(result_type="hits")
        if hits_response.status_code != 200:
            raise ConnectionError("HARVESTING FAILED: CODE {}\n{}".format(hits_response.status_code, hits_response.content))
        xml_response = xml_helper.parse_xml(hits_response.content)

        total_number_to_harvest = int(xml_helper.try_get_attribute_from_xml_element(
            xml_response,
            "numberOfRecordsMatched",
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults"),
        ))

        progress_step_per_request = float(self.max_records_per_request / total_number_to_harvest) * 100

        # Run as long as we can fetch data!
        while self.start_position != 0:
            response = self._get_harvest_response(result_type="results")
            next_record = self._process_harvest_response(response.content)
            self.start_position = next_record
            self._update_pending_task(next_record, total_number_to_harvest, progress_step_per_request)

    def _update_pending_task(self, next_record: int, total_records: int, progress_step: float):
        descr = json.loads(self.pending_task.description)
        descr["phase"] = "Parsing {} of {}".format(next_record, total_records)
        self.pending_task.description = json.dumps(descr)
        self.pending_task.progress += progress_step
        self.pending_task.save()

    def _get_harvest_response(self, result_type: str = "results"):
        harvest_response = None
        if self.method.upper() == "GET":
            params = {
                "service": "CSW",
                "typeNames": "gmd:MD_Metadata",
                "resultType": result_type,
                "startPosition": self.start_position,
                "outputFormat": self.output_format,
                "maxRecords": self.max_records_per_request,
                "version": self.version,
                "request": OGCOperationEnum.GET_RECORDS.value,
            }
            harvest_response = requests.get(
                url=self.harvest_url,
                params=params
            )
        elif self.method.upper() == "POST":
            post_body = self._generate_request_POST_body(self.start_position, result_type=result_type)
            harvest_response = requests.post(self.harvest_url, data=post_body)
        else:
            raise NotImplementedError()

        return harvest_response

    def _process_harvest_response(self, response: bytes):
        xml_response = xml_helper.parse_xml(response)

        next_record = int(xml_helper.try_get_attribute_from_xml_element(
            xml_response,
            "nextRecord",
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults"),
        ))

        # ToDo: Process metadata

        return next_record