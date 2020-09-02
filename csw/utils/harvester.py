"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.07.20

"""
import json
from time import time
from urllib.parse import urlparse, parse_qs
from django.utils import timezone
import pytz
from billiard.context import Process
from dateutil.parser import parse
from django.contrib.gis.geos import Polygon, GEOSGeometry
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction, connections, IntegrityError, DataError
from django.db.models import Q
from django.utils.timezone import utc
from django.utils.translation import gettext_lazy as _
from lxml.etree import Element
from multiprocessing import cpu_count

from MrMap.cacher import PageCacher
from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from MrMap.utils import execute_threads
from api.settings import API_CACHE_KEY_PREFIX
from csw.models import HarvestResult
from csw.settings import csw_logger, CSW_ERROR_LOG_TEMPLATE, CSW_EXTENT_WARNING_LOG_TEMPLATE, HARVEST_METADATA_TYPES, \
    CSW_CACHE_PREFIX, HARVEST_GET_REQUEST_OUTPUT_SCHEMA
from service.helper import xml_helper
from service.helper.enums import OGCOperationEnum, ResourceOriginEnum, MetadataRelationEnum
from service.models import Metadata, Dataset, Keyword, Category, MetadataRelation, MimeType, \
    GenericUrl
from service.settings import DEFAULT_SRS, DEFAULT_SERVICE_BOUNDING_BOX_EMPTY
from structure.models import PendingTask, MrMapGroup, Organization


class Harvester:
    def __init__(self, metadata: Metadata, group: MrMapGroup, max_records_per_request: int = 200):
        self.metadata = metadata
        self.harvesting_group = group
        # Prefer GET url over POST since many POST urls do not work but can still be found in Capabilities
        self.harvest_url = metadata.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_RECORDS.value,
        ).exclude(
            url=None
        ).order_by(
            "method"
        ).first()

        self.version = self.metadata.get_service_version().value
        self.max_records_per_request = max_records_per_request
        self.start_position = 1

        self.method = self.harvest_url.method

        self.harvest_result = HarvestResult(service=self.metadata.service)

        self.harvest_url = getattr(self.harvest_url, "url", None)
        if self.harvest_url is None:
            raise ValueError(_("No get records URL available"))
        self.output_format = getattr(
            self.metadata.get_formats().filter(
                mime_type__icontains="xml"
            ).first(),
            "mime_type",
            None
        )

        if self.output_format is None:
            raise ValueError(_("No XML output format available"))

        self.pending_task = None  # will be initialized in harvest()

        # used for generating a list of already persisted metadata -
        # will be decreased each time the metadata is found during harvest.
        # In the end we have a list of metadata that can be removed from the db
        self.deleted_metadata = set()

        # Used to map parent results of a csw to it's children
        self.parent_child_map = {}

    def harvest(self, task_id: str = None):
        """ Starts harvesting procedure

        Returns:

        """
        # Create a pending task record for the database first!
        task_exists = PendingTask.objects.filter(
            description__icontains=self.metadata.title
        ).exists()
        if task_exists:
            raise ProcessLookupError(_("Harvesting is currently performed"))
        else:
            async_task_id = task_id or self.metadata.id
            self.pending_task = PendingTask.objects.create(
                task_id=async_task_id,
                description=json.dumps({
                    "service": self.metadata.title,
                    "phase": "Connecting...",
                }),
                progress=0,
                remaining_time=None,
                created_by=self.harvesting_group
            )

        # Fill the deleted_metadata with all persisted metadata, so we can eliminate each entry if it is still provided by
        # the catalogue. In the end we will have a list, which contains metadata IDs that are not found in the catalogue anymore.
        all_persisted_metadata_identifiers = Metadata.objects.filter(
            related_metadata__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value,
            related_metadata__metadata_to=self.metadata
        ).values_list(
            "identifier", flat=True
        )
        # Use a set instead of list to increase lookup afterwards
        self.deleted_metadata.update(all_persisted_metadata_identifiers)

        # Perform the initial "hits" request to get an overview of how many data will be fetched
        hits_response, status_code = self._get_harvest_response(result_type="hits")
        descr = json.loads(self.pending_task.description)
        if status_code != 200:
            descr["phase"] = "Harvest failed: HTTP Code {}"
            self.pending_task.description = json.dumps(descr)
            self.pending_task.save()
            raise ConnectionError(_("Harvest failed: Code {}\n{}").format(status_code, hits_response))
        xml_response = xml_helper.parse_xml(hits_response)
        if xml_response is None:
            descr["phase"] = "Response is not a valid xml"
            self.pending_task.description = json.dumps(descr)
            self.pending_task.save()
            raise ConnectionError(_("Response is not a valid xml: \n{}".format(hits_response)))

        try:
            total_number_to_harvest = int(xml_helper.try_get_attribute_from_xml_element(
                xml_response,
                "numberOfRecordsMatched",
                "//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults"),
                ))
        except TypeError:
            csw_logger.error("Malicious Harvest response: {}".format(hits_response))
            descr["phase"] = "Harvest response incorrect. Inform an administrator!"
            self.pending_task.description = json.dumps(descr)
            self.pending_task.save()
            raise AttributeError(_("Harvest response is missing important data!"))

        descr["phase"] = "Start harvesting..."
        self.pending_task.description = json.dumps(descr)
        self.pending_task.save()
        progress_step_per_request = float(self.max_records_per_request / total_number_to_harvest) * 100

        # There are wongly configured CSW, which do not return nextRecord=0 on the last page but instead continue on
        # nextRecord=1. We need to prevent endless loops by checking whether, we already worked on these positions and
        # simply end it there!
        processed_start_positions = set()

        t_start = time()
        number_rest_to_harvest = total_number_to_harvest
        number_of_harvested = 0
        self.harvest_result.timestamp_start = timezone.now()
        self.harvest_result.save()

        page_cacher = PageCacher()

        # Run as long as we can fetch data and as long as the user does not abort the pending task!
        while self.pending_task is not None:
            processed_start_positions.add(self.start_position)
            # Get response
            next_response, status_code = self._get_harvest_response(result_type="results")

            found_entries = self._process_harvest_response(next_response)

            # Calculate time since loop started
            duration = time() - t_start
            number_rest_to_harvest -= self.max_records_per_request
            number_of_harvested += found_entries
            self.harvest_result.number_results = number_of_harvested
            self.harvest_result.save()

            # Remove cached pages of API and CSW
            page_cacher.remove_pages(API_CACHE_KEY_PREFIX)
            page_cacher.remove_pages(CSW_CACHE_PREFIX)
            if self.start_position == 0 or self.start_position in processed_start_positions:
                # We are done!
                estimated_time_for_all = timezone.timedelta(seconds=0)
                break
            else:
                seconds_for_rest = (number_rest_to_harvest * (duration / number_of_harvested))
                estimated_time_for_all = timezone.timedelta(seconds=seconds_for_rest)

            self._update_pending_task(self.start_position, total_number_to_harvest, progress_step_per_request, estimated_time_for_all)

        # Add HarvestResult infos
        self.harvest_result.timestamp_end = timezone.now()
        self.harvest_result.number_results = number_of_harvested
        self.harvest_result.save()

        # Delete Metadata records which could not be found in the catalogue anymore
        # This has to be done if the harvesting run completely. Skip this part if the user aborted the harvest!
        if self.pending_task is not None:
            deleted_metadatas = Metadata.objects.filter(
                identifier__in=self.deleted_metadata
            )
            deleted_metadatas.delete()
            self.pending_task.delete()

        # Remove cached pages of API and CSW
        page_cacher.remove_pages(API_CACHE_KEY_PREFIX)
        page_cacher.remove_pages(CSW_CACHE_PREFIX)

    def _generate_request_POST_body(self, start_position: int, result_type: str = "results"):
        """ Creates a CSW POST body xml document for GetRecords

        Args:
            start_position (int): The start position for the request
        Returns:
             xml (str): The GetRecords xml document
        """
        namespaces = {
            "csw": "http://www.opengis.net/cat/csw/2.0.2",
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
        csw_ns = "{" + namespaces["csw"] + "}"

        root_elem = Element(
            "{}{}".format(csw_ns, OGCOperationEnum.GET_RECORDS.value),
            attrib={
                "version": self.version,
                "service": "CSW",
                "resultType": result_type,
                "outputFormat": self.output_format,
                "startPosition": str(start_position),
                "maxRecords": str(self.max_records_per_request),
                "outputSchema": HARVEST_GET_REQUEST_OUTPUT_SCHEMA,
                #"{}schemaLocation".format(xsi_ns): "http://www.opengis.net/cat/csw/2.0.2",
            },
            nsmap=namespaces
        )
        xml_helper.create_subelement(
            root_elem,
            "{}Query".format(csw_ns),
            None,
            {
                "typeNames": "gmd:MD_Metadata"
            }
        )
        post_content = xml_helper.xml_to_string(root_elem)
        return post_content

    def _update_pending_task(self, next_record: int, total_records: int, progress_step: float, remaining_time):
        """ Updates the PendingTask object

        Args:
            next_record (int): The nextRecord value
            total_records (int): The totalRecord value
            progress_step (int): The increment for the next step
            remaining_time: The timedelta for the remaining time
        Returns:

        """
        try:
            self.pending_task.refresh_from_db()
            descr = json.loads(self.pending_task.description)
            descr["phase"] = _("Harvesting {} of {}").format(next_record, total_records)
            self.pending_task.description = json.dumps(descr)
            self.pending_task.remaining_time = remaining_time
            self.pending_task.progress += progress_step
            self.pending_task.save()
        except ObjectDoesNotExist:
            self.pending_task = None

    def _get_harvest_response(self, result_type: str = "results") -> (bytes, int):
        """ Fetch a response for the harvesting (GetRecords)

        Args:
            result_type (str): Which resultType should be used (hits|results)
        Returns:
             harvest_response (bytes): The response content
             status_code (int): The response status code
        """
        from service.helper.common_connector import CommonConnector
        connector = CommonConnector(
            url=self.harvest_url
        )
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
                "outputSchema": HARVEST_GET_REQUEST_OUTPUT_SCHEMA,
            }
            connector.load(params=params)
            harvest_response = connector.content
        elif self.method.upper() == "POST":
            post_body = self._generate_request_POST_body(self.start_position, result_type=result_type)
            connector.post(
                data=post_body
            )
            harvest_response = connector.content
        else:
            raise NotImplementedError()

        return harvest_response, connector.status_code

    def _process_harvest_response(self, next_response: bytes) -> int:
        """ Processes the harvest response content

        While the last response is being processed, the next one is already loaded to decrease run time

        Args:
            response (bytes): The response as bytes
        Returns:
             number_found_entries (int): The amount of found metadata records in this response
        """
        xml_response = xml_helper.parse_xml(next_response)
        if xml_response is None:
            csw_logger.error(
                "Response is no valid xml. catalogue: {}, startPosition: {}, maxRecords: {}".format(
                    self.metadata.title,
                    self.start_position,
                    self.max_records_per_request
                )
            )
            # Abort!
            self.start_position = 0
            return

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

        # Fetch found identifiers in parent process, so self.deleted_metadata can be edited easily
        for md_identifier in md_metadata_entries:
            id = xml_helper.try_get_text_from_xml_element(
                md_identifier,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("fileIdentifier")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            try:
                self.deleted_metadata.remove(id)
            except KeyError:
                pass

        # Delete response to free memory
        del xml_response

        # Process response via multiple processes
        t_start = time()
        num_processes = int(cpu_count()/2)
        num_processes = num_processes if num_processes >= 1 else 1
        index_step = int(len(md_metadata_entries)/num_processes)
        start_index = 0
        end_index = 0
        self.resource_list = md_metadata_entries
        process_list = []
        for i in range(0, num_processes):
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

        csw_logger.debug(
            "Harvesting '{}': runtime for {} metadata parsing: {}s ####".format(
                self.metadata.title,
                self.max_records_per_request,
                time() - t_start
            )
        )
        return len(md_metadata_entries)

    def _create_metadata_from_md_metadata(self, start_index, end_index):
        """ Creates Metadata records from raw xml md_metadata data.

        Runs multiprocessed. Therefore only a start_index and end_index is given, since each process reads from the
        same parent process resource_list.

        Args:
            start_index (int): The start index
            end_index (int): The end index
        Returns:
        """
        if end_index < 0:
            md_metadata_entries = self.resource_list
        else:
            md_metadata_entries = self.resource_list[start_index:end_index]
        md_data = self._md_metadata_parse_to_dict(md_metadata_entries)

        for md_data_entry in md_data:
            self._persist_metadata(md_data_entry)

        self._persist_metadata_parent_relation()

    def _persist_metadata(self, md_data_entry: dict):
        """ Creates real Metadata model records from the parsed data

        Args:
            md_data_entry (dict):
        Returns:
             metadata (Metadata): The persisted metadata object
        """
        _id = md_data_entry["id"]
        # Remove this id from the set of metadata which shall be deleted in the end.
        try:
            self.deleted_metadata.remove(_id)
        except KeyError:
            pass

        try:
            md = Metadata.objects.get(
                identifier=_id,
            )
            is_new = False
            if md.last_remote_change == md_data_entry["date_stamp"]:
                # Nothing to do here!
                return
        except ObjectDoesNotExist:
            md = Metadata(
                identifier=_id
            )
            is_new = True
        md.access_constraints = md_data_entry.get("access_constraints", None)
        md.created_by = self.harvesting_group
        md.origin = ResourceOriginEnum.CATALOGUE.value
        md.last_remote_change = md_data_entry.get("date_stamp", None)
        md.title = md_data_entry.get("title", None)
        md.public_id = md.generate_public_id()
        md.contact = md_data_entry.get("contact", None)
        md.language_code = md_data_entry.get("language_code", None)
        md.metadata_type = md_data_entry.get("metadata_type", None)
        md.abstract = md_data_entry.get("abstract", None)
        md.bounding_geometry = md_data_entry.get("bounding_geometry", None)
        formats = md_data_entry.get("formats", [])
        md.is_active = True
        md.capabilities_original_uri = md_data_entry.get("capabilities_original_url", None)
        try:
            # Improve speed for keyword get-create by fetching (filter) all existing ones and only perform
            # get_or_create on the ones that do not exist yet. Speed up by ~50% for large amount of data
            existing_kws = Keyword.objects.filter(keyword__in=md_data_entry["keywords"])
            existing_kws = [kw.keyword for kw in existing_kws]
            new_kws = [kw for kw in md_data_entry["keywords"] if kw not in existing_kws]
            [Keyword.objects.get_or_create(keyword=kw)[0] for kw in new_kws]
            kws = Keyword.objects.filter(keyword__in=md_data_entry["keywords"])

            # Same for MimeTypes
            existing_formats = MimeType.objects.filter(mime_type__in=md_data_entry["formats"])
            existing_formats = [_format.mime_type for _format in existing_formats]
            new_formats = [_format for _format in md_data_entry["formats"] if _format not in existing_formats]
            [MimeType.objects.get_or_create(mime_type=_format)[0] for _format in new_formats]
            formats = MimeType.objects.filter(mime_type__in=md_data_entry["formats"])

            with transaction.atomic():
                if len(md_data_entry["categories"]) > 0:
                    q = Q()
                    for cat in md_data_entry["categories"]:
                        q |= Q(title_EN__iexact=cat)
                    categories = Category.objects.filter(q)
                else:
                    categories = []

                for link in md_data_entry.get("links", []):
                    url = link.get("link", None)
                    if url is None:
                        continue
                    generic_url = GenericUrl()
                    generic_url.description = "[HARVESTED URL] \n{}".format(link.get("description", ""))
                    generic_url.method = "Get"
                    generic_url.url = url
                    generic_url.save()
                    md.additional_urls.add(generic_url)

                md.save(add_monitoring=False)
                md.keywords.add(*kws)
                md.categories.add(*categories)
                md.formats.add(*formats)

                # To reduce runtime, we only create a new MetadataRelation if we are sure there hasn't already been one.
                # Using get_or_create increases runtime on existing metadata too much!
                if is_new:
                    md.related_metadata.add(
                        MetadataRelation.objects.create(
                            relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value,
                            metadata_to=self.metadata,
                            origin=ResourceOriginEnum.CATALOGUE.value
                        )
                    )

            parent_id = md_data_entry["parent_id"]
            # Add the found parent_id to the parent_child map!
            if parent_id is not None:
                if self.parent_child_map.get(parent_id, None) is None:
                    self.parent_child_map[parent_id] = [md]
                else:
                    self.parent_child_map[parent_id].append(md)

        except (IntegrityError, DataError) as e:
            csw_logger.error(
                CSW_ERROR_LOG_TEMPLATE.format(
                    md.identifier,
                    self.metadata.title,
                    e
                )
            )

    @transaction.atomic
    def _persist_metadata_parent_relation(self):
        """ Creates MetadataRelation records if there is information about a parent-child relation

        Args:
            md_data_entry (dict):
        Returns:
             metadata (Metadata): The persisted metadata object
        """
        # Make sure there is some kind of parent-subelement relation. We can not use the regular Service.parent_service
        # model since there is not enough data from the CSW to use Service properly and we can not 100% determine which
        # types of Servives we are dealing with (WFS/WMS). Therefore for harvesting, we need to use this workaround using
        # MetadataRelation

        for parent_id, children in self.parent_child_map.items():
            try:
                parent_md = Metadata.objects.get(
                    identifier=parent_id
                )
            except ObjectDoesNotExist:
                # it seems that this metadata has not been harvested yet - we keep it in the map for later!
                continue
            for child in children:
                # Check if relation already exists - again a faster alternative to get_or_create
                rel_exists = child.related_metadata.filter(
                    metadata_to=parent_md,
                    relation_type=MetadataRelationEnum.HARVESTED_PARENT.value,
                    origin=ResourceOriginEnum.CATALOGUE.value,
                ).exists()
                if not rel_exists:
                    md_relation = MetadataRelation.objects.create(
                        relation_type=MetadataRelationEnum.HARVESTED_PARENT.value,
                        metadata_to=parent_md,
                        origin=ResourceOriginEnum.CATALOGUE.value
                    )
                    child.related_metadata.add(md_relation)

            # clear children list of parent afterwards so we don't work on them again
            self.parent_child_map[parent_id] = []

    def _md_metadata_parse_to_dict(self, md_metadata_entries: list) -> list:
        """ Read most important data from MD_Metadata xml element

        Args:
            md_metadata_entries (list): The xml MD_Metadata elements
        Returns:
             ret_list (list): The list containing dicts
        """
        ret_list = []
        for md_metadata in md_metadata_entries:
            md_data_entry = {}

            # Check before anything else, whether this metadata type can be skipped!
            hierarchy_level = xml_helper.try_get_attribute_from_xml_element(
                md_metadata,
                "codeListValue",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("hierarchyLevel")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("MD_ScopeCode")
            )
            metadata_type = hierarchy_level
            md_data_entry["metadata_type"] = metadata_type
            if not HARVEST_METADATA_TYPES.get(metadata_type, False):
                continue

            _id = xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("fileIdentifier")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            md_data_entry["id"] = _id

            parent_id = xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("parentIdentifier")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            md_data_entry["parent_id"] = parent_id

            # A workaround, so we do not need to check whether SV_ServiceIdentification or MD_DataIdentification is present
            # in this metadata: Simply take the direct parent and perform a deeper nested search on the inside of this element.
            # Yes, we could simply decide based on the hierarchyLevel attribute whether to search for SV_xxx or MD_yyy.
            # No, there are metadata entries which do not follow these guidelines and have "service" with MD_yyy
            # Yes, they are important since they can be found in the INSPIRE catalogue (07/2020)
            identification_elem = xml_helper.try_get_single_element_from_xml(
                xml_elem=md_metadata,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("identificationInfo")
            )
            title = xml_helper.try_get_text_from_xml_element(
                identification_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("citation")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Citation")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("title")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            md_data_entry["title"] = title

            language_code = xml_helper.try_get_attribute_from_xml_element(
                md_metadata,
                "codeListValue",
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("language")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("LanguageCode")
            )
            md_data_entry["language_code"] = language_code

            date_stamp = xml_helper.try_get_text_from_xml_element(
                md_metadata,
                "./" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Date")
            ) or xml_helper.try_get_text_from_xml_element(
                md_metadata,
                "./" + GENERIC_NAMESPACE_TEMPLATE.format("dateStamp")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("DateTime")
            )
            try:
                md_data_entry["date_stamp"] = parse(date_stamp).replace(tzinfo=utc)
            except TypeError:
                md_data_entry["date_stamp"] = None

            abstract = xml_helper.try_get_text_from_xml_element(
                md_metadata,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("abstract")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            md_data_entry["abstract"] = abstract

            digital_transfer_elements = xml_helper.try_get_element_from_xml(
                xml_elem=md_metadata,
                elem=".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_DigitalTransferOptions")
            )
            links = []
            for elem in digital_transfer_elements:
                links_entry = {}
                resource_link = xml_helper.try_get_text_from_xml_element(
                    elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("onLine")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CI_OnlineResource")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("linkage")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("URL"),
                )
                descr = xml_helper.try_get_text_from_xml_element(
                    elem,
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("onLine")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CI_OnlineResource")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("description")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
                )
                links_entry["link"] = resource_link
                links_entry["description"] = descr

                if resource_link is not None:
                    # Check on the type of online_resource we found -> could be GetCapabilities
                    query_params = parse_qs(urlparse(resource_link.lower()).query)
                    if OGCOperationEnum.GET_CAPABILITIES.value.lower() in query_params.get("request", []):
                        # Parse all possibly relevant data from the dict
                        version = query_params.get("version", [None])
                        service_type = query_params.get("service", [None])
                        md_data_entry["capabilities_original_url"] = resource_link
                        md_data_entry["service_type"] = service_type[0]
                        md_data_entry["version"] = version[0]
                links.append(links_entry)

            md_data_entry["links"] = links

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
                    ) or "0.0",
                    xml_helper.try_get_text_from_xml_element(
                        bbox_elem,
                        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("southBoundLatitude")
                        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                    ) or "0.0",
                    xml_helper.try_get_text_from_xml_element(
                        bbox_elem,
                        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("eastBoundLongitude")
                        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                    ) or "0.0",
                    xml_helper.try_get_text_from_xml_element(
                        bbox_elem,
                        ".//" + GENERIC_NAMESPACE_TEMPLATE.format("northBoundLatitude")
                        + "/" + GENERIC_NAMESPACE_TEMPLATE.format("Decimal")
                    ) or "0.0",
                ]
                # There are metadata with wrong vertex notations like 50,3 instead of 50.3
                # We should just drop them, since they are not compatible with the specifications but in here, we make an
                # exception and replace , since it's quite easy
                extent = [vertex.replace(",", ".") for vertex in extent]
                try:
                    bounding_geometry = GEOSGeometry(Polygon.from_bbox(bbox=extent), srid=DEFAULT_SRS)
                except Exception:
                    # Log malicious extent!
                    csw_logger.warning(
                        CSW_EXTENT_WARNING_LOG_TEMPLATE.format(
                            _id,
                            self.metadata.title,
                            extent
                        )
                    )
                    bounding_geometry = DEFAULT_SERVICE_BOUNDING_BOX_EMPTY
            else:
                bounding_geometry = DEFAULT_SERVICE_BOUNDING_BOX_EMPTY

            md_data_entry["bounding_geometry"] = bounding_geometry
            md_data_entry["contact"] = self._create_contact_from_md_metadata(md_metadata)
            md_data_entry["formats"] = self._create_formats_from_md_metadata(md_metadata)

            # Load non-metadata data
            # ToDo: Should harvesting persist non-metadata data?!
            #described_resource = None
            #metadata = None
            #if hierarchy_level == MetadataEnum.DATASET.value:
            #    described_resource = self._create_dataset_from_md_metadata(md_metadata, metadata)
            #    described_resource.metadata = metadata
            #    described_resource.is_active = True
            #    described_resource.save()

            ret_list.append(md_data_entry)
        return ret_list

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

    def _create_formats_from_md_metadata(self, md_metadata: Element) -> list:
        """ Creates a list of MimeType objects from MD_Metadata element

        Args:
            md_metadata (Element): The xml element
        Returns:
             formats (list)
        """
        formats = []
        distribution_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("distributionFormat"),
            md_metadata
        )
        if distribution_elem is None:
            return formats
        md_format_elems = xml_helper.try_get_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("MD_Format"),
            md_metadata
        )
        for md_format_elem in md_format_elems:
            name = xml_helper.try_get_text_from_xml_element(
                md_format_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("name")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            )
            if name is not None:
                formats.append(name)
        return formats

    def _create_contact_from_md_metadata(self, md_metadata: Element) -> Organization:
        """ Creates an Organization (Contact) instance from MD_Metadata.

        Holds the basic information

        Args:
            md_metadata (Element): The xml element
        Returns:
             org (Organization): The organization element
        """
        resp_party_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_ResponsibleParty"),
            md_metadata
        )
        if resp_party_elem is None:
            return None

        organization_name = xml_helper.try_get_text_from_xml_element(
            resp_party_elem,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("organisationName")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        ) or ""
        person_name = xml_helper.try_get_text_from_xml_element(
            resp_party_elem,
            "./" + GENERIC_NAMESPACE_TEMPLATE.format("individualName")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        ) or ""
        phone = xml_helper.try_get_text_from_xml_element(
            resp_party_elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Telephone")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("voice")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        ) or ""
        facsimile = xml_helper.try_get_text_from_xml_element(
            resp_party_elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Telephone")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("facsimile")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
        ) or ""

        # Parse address information, create fallback values
        address = ""
        city = ""
        postal_code = ""
        country = ""
        email = ""
        state = ""
        address_elem = xml_helper.try_get_single_element_from_xml(
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_Address"),
            md_metadata
        )
        if address_elem is not None:
            address = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("deliveryPoint")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
            city = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("city")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
            postal_code = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("postalCode")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
            country = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("country")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
            email = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("electronicMailAddress")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
            state = xml_helper.try_get_text_from_xml_element(
                address_elem,
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("administrativeArea")
                + "/" + GENERIC_NAMESPACE_TEMPLATE.format("CharacterString")
            ) or ""
        is_auto_generated = True
        description = xml_helper.try_get_text_from_xml_element(
            resp_party_elem,
            ".//" + GENERIC_NAMESPACE_TEMPLATE.format("CI_OnlineResource")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("linkage")
            + "/" + GENERIC_NAMESPACE_TEMPLATE.format("URL")
        ) or ""
        try:
            org = Organization.objects.create(
                person_name=person_name,
                organization_name=organization_name,
                phone=phone,
                facsimile=facsimile,
                address=address,
                city=city,
                postal_code=postal_code,
                country=country,
                email=email,
                state_or_province=state,
                is_auto_generated=is_auto_generated,
                description=description,
            )
        except IntegrityError:
            org = Organization.objects.get(
                person_name=person_name,
                organization_name=organization_name,
                phone=phone,
                facsimile=facsimile,
                address=address,
                city=city,
                postal_code=postal_code,
                country=country,
                email=email,
                state_or_province=state,
                is_auto_generated=is_auto_generated,
                description=description,
            )
        return org