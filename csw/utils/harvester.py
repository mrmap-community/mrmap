"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
import json
from time import time
import datetime

import requests
from django.contrib.gis.geos import Polygon, GEOSGeometry
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction, connections
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from lxml.etree import Element
from multiprocessing import Process

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from MrMap.utils import execute_threads
from service.helper import xml_helper
from service.helper.enums import OGCOperationEnum, ResourceOriginEnum
from service.models import Metadata, Dataset, Keyword, Category
from service.settings import DEFAULT_SRS, DEFAULT_SERVICE_BOUNDING_BOX_EMPTY
from structure.models import PendingTask, MrMapGroup


class Harvester:
    def __init__(self, metadata: Metadata, group: MrMapGroup, max_records_per_request: int = 200):
        self.metadata = metadata
        self.harvesting_group = group
        self.harvest_url = metadata.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_RECORDS.value,
        ).exclude(
            url=None
        ).first()

        self.version = self.metadata.get_service_version().value
        self.max_records_per_request = max_records_per_request
        self.start_position = 1

        self.method = self.harvest_url.method

        self.harvest_url = getattr(self.harvest_url, "url", None)
        if self.harvest_url is None:
            raise ValueError(_("No get records URL available"))
        self.output_format = getattr(
            self.metadata.formats.filter(
                mime_type__icontains="xml"
            ).first(),
            "mime_type",
            None
        )

        if self.output_format is None:
            raise ValueError(_("No XML output format available"))

        self.pending_task = None  # will be initialized in harvest()
        self.next_response = None

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
        )
        is_new = self.pending_task[1]
        self.pending_task = self.pending_task[0]

        if not is_new:
            raise ProcessLookupError(_("Harvesting is currently performed. Remaining time: {}").format(self.pending_task.remaining_time))
        else:
            self.pending_task.description = json.dumps({
                "service": self.metadata.title,
                "phase": "Loading Harvest...",
            })
            self.pending_task.progress = 0
            self.pending_task.save()

        # Perform the initial "hits" request to get an overview of how many data will be fetched
        hits_response = self._get_harvest_response(result_type="hits")
        if hits_response.status_code != 200:
            raise ConnectionError(_("Harvest failed: Code {}\n{}").format(hits_response.status_code, hits_response.content))
        xml_response = xml_helper.parse_xml(hits_response.content)

        total_number_to_harvest = int(xml_helper.try_get_attribute_from_xml_element(
            xml_response,
            "numberOfRecordsMatched",
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults"),
            ))

        progress_step_per_request = float(self.max_records_per_request / total_number_to_harvest) * 100

        t_start = time()
        # Run as long as we can fetch data!
        while self.start_position != 0:
            # Get response
            next_response = self._get_harvest_response(result_type="results", only_content=True)

            self._process_harvest_response(next_response)

            # Calculate remaining time
            duration = time() - t_start
            if self.start_position == 0:
                # We are done!
                estimated_time_for_all = datetime.timedelta(seconds=0)
            else:
                estimated_time_for_all = datetime.timedelta(seconds=((total_number_to_harvest - self.start_position) * (duration / self.start_position)))
            self._update_pending_task(self.start_position, total_number_to_harvest, progress_step_per_request, estimated_time_for_all)

        self.pending_task.delete()

    def _update_pending_task(self, next_record: int, total_records: int, progress_step: float, remaining_time):
        """ Updates the PendingTask object

        Args:
            next_record (int): The nextRecord value
            total_records (int): The totalRecord value
            progress_step (int): The increment for the next step
            remaining_time: The timedelta for the remaining time
        Returns:

        """
        descr = json.loads(self.pending_task.description)
        descr["phase"] = _("Harvesting {} of {}").format(next_record, total_records)
        self.pending_task.description = json.dumps(descr)
        self.pending_task.remaining_time = remaining_time
        self.pending_task.progress += progress_step
        self.pending_task.save()

    def _get_harvest_response(self, result_type: str = "results", only_content: bool = False):
        """ Fetch a response for the harvesting (GetRecords)

        Args:
            result_type (str): Which resultType should be used (hits|results)
        Returns:
             harvest_response (bytes): The response content
        """
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

        response = harvest_response if not only_content else harvest_response.content
        return response

    def _process_harvest_response(self, next_response: bytes):
        """ Processes the harvest response content

        While the last response is being processed, the next one is already loaded to decrease run time

        Args:
            response (bytes): The response as bytes
        Returns:
             next_record (int): The nextRecord value (used for next startPosition)
        """
        xml_response = xml_helper.parse_xml(next_response)
        md_metadata_entries = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_Metadata"),
            xml_response
        ) or []
        next_record_position = int(xml_helper.try_get_attribute_from_xml_element(
            xml_response,
            "nextRecord",
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults"),
        ))
        self.start_position = next_record_position

        # Delete response to free memory
        del xml_response

        # Process response via multiple processes
        t_start = time()
        num_threads = 10
        index_step = int(len(md_metadata_entries)/num_threads)
        start_index = 0
        end_index = 0
        self.resource_list = md_metadata_entries
        process_list = []
        for i in range(0, num_threads):
            if index_step < 1:
                end_index = -1
            else:
                end_index += index_step
            p = Process(target=self._create_metadata_from_md_metadata, args=(start_index, end_index))
            start_index += index_step
            process_list.append(p)
        # Close all connections to force each process to create a new one for itself
        connections.close_all()
        execute_threads(process_list)

        print("#### TOTAL TIME FOR MD CREATION: {}s ####".format(time() - t_start))

    @transaction.atomic
    def _create_metadata_from_md_metadata(self, start_index, end_index):
        """ Creates Metadata records from raw xml md_metadata data
        Args:
            md_metadata_entries (list): The list of xml objects
        Returns:
        """
        if end_index < 0:
            md_metadata_entries = self.resource_list
        else:
            md_metadata_entries = self.resource_list[start_index:end_index]
        md_data = [self._md_metadata_parse_to_dict(md_metadata) for md_metadata in md_metadata_entries]

        for md_data_entry in md_data:
            try:
                md = Metadata.objects.get(
                    id=md_data_entry["id"],
                    identifier=md_data_entry["id"],
                )
            except ObjectDoesNotExist:
                md = Metadata(
                    id=md_data_entry["id"],
                    identifier=md_data_entry["id"]
                )
            md.access_constraints = md_data_entry.get("access_constraints", None)
            md.created_by = self.harvesting_group
            md.origin = ResourceOriginEnum.CATALOGUE.value
            md.title = md_data_entry.get("title", None)
            md.public_id = md.generate_public_id()
            md.language_code = md_data_entry.get("language_code", None)
            md.metadata_type = md_data_entry.get("metadata_type", None)
            md.abstract = md_data_entry.get("abstract", None)
            md.bounding_geometry = md_data_entry.get("bounding_geometry", None)
            md.is_active = True
            # Improve speed for keyword get-create by fetching (filter) all existing ones and only perform
            # get_or_create on the ones that do not exist yet. Speed up by ~50% for large amount of data
            existing_kws = Keyword.objects.filter(keyword__in=md_data_entry["keywords"])
            existing_kws = [kw.keyword for kw in existing_kws]
            new_kws = [kw for kw in md_data_entry["keywords"] if kw not in existing_kws]
            [Keyword.objects.get_or_create(keyword=kw)[0] for kw in new_kws]
            kws = Keyword.objects.filter(keyword__in=md_data_entry["keywords"])
            q = Q()
            for cat in md_data_entry["categories"]:
                q |= Q(title_EN__iexact=cat)
            categories = Category.objects.filter(q)
            md.save(add_monitoring=False)
            md.keywords.add(*kws)
            md.categories.add(*categories)

    def _create_dataset_from_md_metadata(self, md_metadata: Element, metadata: Metadata) -> Dataset:
        """ Creates a Dataset record from xml data
        Args:
            md_metadata (Element): The xml element which holds the data
            metadata (Metadata): The related metadata element
        Returns:
            dataset (Dataset): The dataset record
        """
        dataset = Dataset()
        dataset.language_code = metadata.language_code
        dataset.language_code_list_url = xml_helper.try_get_attribute_from_xml_element(
            md_metadata,
            "codeList",
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("language")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode")
        )
        dataset.character_set_code = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("characterSet")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode")
        )
        dataset.character_set_code_list_url = xml_helper.try_get_attribute_from_xml_element(
            md_metadata,
            "codeList",
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("characterSet")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_CharacterSetCode")
        )
        dataset.date_stamp = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Date")
        )
        dataset.metadata_standard_name = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("metadataStandardName")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        dataset.metadata_standard_version = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("metadataStandardVersion")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        dataset.update_frequency_code = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_MaintenanceFrequencyCode")
        )
        dataset.update_frequency_code_list_url = xml_helper.try_get_attribute_from_xml_element(
            md_metadata,
            "codeList",
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_MaintenanceFrequencyCode")
        )
        dataset.use_limitation = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("useLimitation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        dataset.lineage_statement = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("statement")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        return dataset

    def _md_metadata_parse_to_dict(self, md_metadata: Element) -> dict:
        """ Read most important data from MD_Metadata xml element and return as a dict
        Args:
            md_metadata (Element): The xml element of MD_Metadata
        Returns:
             md_data_entry (dict): The dict containing data
        """
        md_data_entry = {}
        _id = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("fileIdentifier")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        md_data_entry["id"] = _id
        title = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DataIdentification")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("citation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Citation")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("title")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        md_data_entry["title"] = title
        language_code = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("language")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode")
        )
        md_data_entry["language_code"] = language_code
        hierarchy_level = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("hierarchyLevel")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_ScopeCode")
        )
        metadata_type = hierarchy_level
        md_data_entry["metadata_type"] = metadata_type
        abstract = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("abstract")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        md_data_entry["abstract"] = abstract
        keywords = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("keyword")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString"),
            md_metadata,
        ) or []
        keywords = [
            xml_helper.try_get_text_from_xml_element(
                kw
            )
            for kw in keywords
        ]
        md_data_entry["keywords"] = keywords
        access_constraints = xml_helper.try_get_text_from_xml_element(
            md_metadata,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("otherConstraints")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        )
        md_data_entry["access_constraints"] = access_constraints
        categories = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_TopicCategoryCode"),
            md_metadata,
        ) or []
        categories = [
            xml_helper.try_get_text_from_xml_element(
                cat
            )
            for cat in categories
        ]
        md_data_entry["categories"] = categories
        bbox_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("EX_GeographicBoundingBox"),
            md_metadata
        )
        if bbox_elem is not None:
            extent = [
                xml_helper.try_get_text_from_xml_element(
                    bbox_elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("westBoundLongitude")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                ),
                xml_helper.try_get_text_from_xml_element(
                    bbox_elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("southBoundLatitude")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                ),
                xml_helper.try_get_text_from_xml_element(
                    bbox_elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("eastBoundLongitude")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                ),
                xml_helper.try_get_text_from_xml_element(
                    bbox_elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("northBoundLatitude")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                ),
            ]
            bounding_geometry = GEOSGeometry(Polygon.from_bbox(bbox=extent), srid=DEFAULT_SRS)
        else:
            bounding_geometry = DEFAULT_SERVICE_BOUNDING_BOX_EMPTY
        md_data_entry["bounding_geometry"] = bounding_geometry
        # Load non-metadata data
        # ToDo: Should harvesting persist non-metadata data?!
        #described_resource = None
        #metadata = None
        #if hierarchy_level == MetadataEnum.DATASET.value:
        #    described_resource = self._create_dataset_from_md_metadata(md_metadata, metadata)
        #    described_resource.metadata = metadata
        #    described_resource.is_active = True
        #    described_resource.save()
        return md_data_entry
