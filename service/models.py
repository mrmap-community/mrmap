import uuid
from collections import OrderedDict

from dateutil.parser import parse
from lxml import etree

from django.contrib.gis.geos import Polygon
from django.db import models, transaction
from django.contrib.gis.db import models
from django.utils import timezone
from lxml.etree import Element

from MapSkinner.settings import XML_NAMESPACES, HOST_NAME, HTTP_OR_SSL
from service.helper.enums import ServiceTypes
from structure.models import Group, Organization
from service.helper import xml_helper


class Keyword(models.Model):
    keyword = models.CharField(max_length=255)

    def __str__(self):
        return self.keyword


class Resource(models.Model):
    uuid = models.CharField(max_length=255, default=uuid.uuid4())
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Group, on_delete=models.DO_NOTHING, null=True, blank=True)
    last_modified = models.DateTimeField(null=True)
    is_deleted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        # We always want to have automatically the last timestamp from the latest change!
        self.last_modified = timezone.now()
        super().save()

    class Meta:
        abstract = True

class MetadataOrigin(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class MetadataRelation(models.Model):
    metadata_from = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadata_from")
    metadata_to = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadata_to")
    relation_type = models.CharField(max_length=255, null=True, blank=True)
    internal = models.BooleanField(default=False)
    origin = models.ForeignKey(MetadataOrigin, on_delete=models.CASCADE)

    def __str__(self):
        return "{} {} {}".format(self.metadata_from.title, self.relation_type, self.metadata_to.title)


class Metadata(Resource):
    identifier = models.CharField(max_length=255, null=True)
    title = models.CharField(max_length=255)
    abstract = models.TextField(null=True, blank=True)
    online_resource = models.CharField(max_length=500, null=True, blank=True)  # where the service data can be found
    capabilities_original_uri = models.CharField(max_length=500, blank=True, null=True)
    service_metadata_original_uri = models.CharField(max_length=500, blank=True, null=True)

    contact = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, blank=True, null=True)
    terms_of_use = models.ForeignKey('TermsOfUse', on_delete=models.DO_NOTHING, null=True)
    access_constraints = models.TextField(null=True, blank=True)
    fees = models.TextField(null=True, blank=True)

    last_remote_change = models.DateTimeField(null=True, blank=True)  # the date time, when the metadata was changed where it comes from
    status = models.IntegerField(null=True)
    inherit_proxy_uris = models.BooleanField(default=False)
    spatial_res_type = models.CharField(max_length=100, null=True)
    spatial_res_value = models.CharField(max_length=100, null=True)
    is_broken = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    is_inspire_conform = models.BooleanField(default=False)
    has_inspire_downloads = models.BooleanField(default=False)
    bounding_geometry = models.PolygonField(null=True, blank=True)

    # capabilities
    dimension = models.CharField(max_length=100, null=True)
    authority_url = models.CharField(max_length=255, null=True)
    metadata_url = models.CharField(max_length=255, null=True)

    # other
    keywords = models.ManyToManyField(Keyword)
    categories = models.ManyToManyField('Category')
    reference_system = models.ManyToManyField('ReferenceSystem')
    metadata_type = models.ForeignKey('MetadataType', on_delete=models.DO_NOTHING, null=True, blank=True)

    ## for ISO metadata
    dataset_id = models.CharField(max_length=255, null=True, blank=True)
    dataset_id_code_space = models.CharField(max_length=255, null=True, blank=True)

    related_metadata = models.ManyToManyField(MetadataRelation)
    origin = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.keywords_list = []
        self.reference_system_list = []

    def __str__(self):
        return self.title

    def delete(self, using=None, keep_parents=False):
        """ Overwriting of the regular delete function

        Checks if the current processed metadata is part of a MetadataRelation, which indicates, that it is still used
        somewhere else, maybe by another service. If there is only one MetadataRelation found for this metadata record,
        we can delete it safely..

        Args:
            using: The regular 'using' parameter
            keep_parents: The regular 'keep_parents' parameter
        Returns:
            nothing
        """
        # check if there are MetadataRelations on this metadata record
        # if so, we can not remove it until these relations aren't used anymore
        dependencies = MetadataRelation.objects.filter(
            metadata_to=self
        )
        if dependencies.count() > 1:
            # if there are more than one dependency, we should not remove it
            # the one dependency we can expect at least is the relation to the current metadata record
            return
        else:
            # if we have one or less relations to this metadata record, we can remove it anyway
            super().delete(using, keep_parents)

    def get_service_type(self):
        """ Performs a check on which service type is described by the metadata record

        Returns:
             service_type (str): The service type as string ('wms' or 'wfs')
        """
        service_type = None
        if self.is_root():
            return self.service.servicetype.name
        elif self.metadata_type.type == 'layer':
            service_type = 'wms'
        elif self.metadata_type.type == 'featuretype':
            service_type = 'wfs'
        return service_type

    def find_max_bounding_box(self):
        """ Returns the largest bounding box of all children

        Saves the found bounding box to bounding_geometry for faster access

        Returns:

        """
        children = self.service.child_service.all()
        max_box = None
        for child in children:
            bbox = child.layer.bbox_lat_lon
            if max_box is None:
                max_box = bbox
            else:
                ba = bbox.area
                ma = max_box.area
                if ba > ma:
                    max_box = bbox
        self.bounding_geometry = max_box
        self.save()
        return max_box

    def is_root(self):
        """ Checks whether the metadata describes a root service or a layer/featuretype

        Returns:
             is_root (bool): True if there is no parent service to the described service, False otherwise
        """
        return self.metadata_type.type == 'service'

    def _restore_layer_md(self, service, identifier: str = None):
        """ Private function for retrieving single layer metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
            identifier (str): The identifier string of the layer
        Returns:
             nothing, it changes the Metadata object itself
        """
        # parse single layer
        identifier = self.service.layer.identifier
        layer = service.get_layer_by_identifier(identifier)
        self.title = layer.title
        self.abstract = layer.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in layer.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        original_iso_links = [x.uri for x in layer.iso_metadata]
        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in original_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.service.parent_service.metadata
        cap_doc = Document.objects.get(related_metadata=rel_md)
        cap_doc.restore_subelement(identifier)
        return

    def _restore_feature_type_md(self, service, identifier: str = None):
        """ Private function for retrieving single featuretype metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
            identifier (str): The identifier string of the layer
        Returns:
             nothing, it changes the Metadata object itself
        """
        # parse single layer
        identifier = self.identifier
        f_t = service.get_feature_type_by_identifier(identifier)
        f_t_obj = f_t.get("feature_type", None)
        f_t_iso_links = f_t.get("dataset_md_list", [])
        self.title = f_t_obj.metadata.title
        self.abstract = f_t_obj.metadata.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in f_t_obj.metadata.keywords_list:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in f_t_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.featuretype.service.metadata
        cap_doc = Document.objects.get(related_metadata=rel_md)
        cap_doc.restore_subelement(identifier)
        return

    def _restore_wms(self, identifier: str = None):
        """ Restore the metadata of a wms service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wms import OGCWebMapServiceFactory
        from service.helper import service_helper
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        service = OGCWebMapServiceFactory()
        service = service.get_ogc_wms(version=service_version, service_connect_url=self.capabilities_original_uri)
        service.get_capabilities()
        service.create_from_capabilities(metadata_only=True)

        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_layer_md(service, identifier)

        self.title = service.service_identification_title
        self.abstract = service.service_identification_abstract
        self.access_constraints = service.service_identification_accessconstraints
        keywords = service.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.inherit_proxy_uris = False

        cap_doc = Document.objects.get(related_metadata=self)
        cap_doc.restore()

    def _restore_wfs(self, identifier: str = None):
        """ Restore the metadata of a wfs service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper

        # Prepare 'service' for further handling
        # If no identifier is provided, we deal with a root metadata
        is_root = identifier is None
        if is_root:
            service = self.service
        else:
            service = self.featuretype.service
        service_version = service_helper.resolve_version_enum(service.servicetype.version)
        service_tmp = OGCWebFeatureServiceFactory()
        service_tmp = service_tmp.get_ogc_wfs(version=service_version, service_connect_url=self.capabilities_original_uri)
        if service_tmp is None:
            return
        service_tmp.get_capabilities()
        service_tmp.create_from_capabilities(metadata_only=True)
        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_feature_type_md(service_tmp, identifier)

        self.title = service_tmp.service_identification_title
        self.abstract = service_tmp.service_identification_abstract
        self.access_constraints = service_tmp.service_identification_accessconstraints
        keywords = service_tmp.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.inherit_proxy_uris = False

        cap_doc = Document.objects.get(related_metadata=service.metadata)
        cap_doc.restore()

    def restore(self, identifier: str = None):
        """ Load original metadata from capabilities and ISO metadata

        Args:
            identifier (str): The identifier of a featureType or Layer (in xml often named 'name')
        Returns:
             nothing
        """

        # identify whether this is a wfs or wms (we need to handle them in different ways)
        service_type = self.get_service_type()
        if service_type == 'wfs':
            self._restore_wfs(identifier)
        elif service_type == 'wms':
            self._restore_wms(identifier)

    def get_related_metadata_uris(self):
        """ Generates a list of all related metadata online links and returns them

        Returns:
             links (list): A list containing all online links of related metadata
        """
        rel_mds = self.related_metadata.all()
        links = []
        for md in rel_mds:
            links.append(md.metadata_to.metadata_url)
        return links


class MetadataType(models.Model):
    type = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.type



class Document(Resource):
    related_metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE)
    original_capability_document = models.TextField(null=True, blank=True)
    current_capability_document = models.TextField(null=True, blank=True)
    service_metadata_document = models.TextField(null=True, blank=True)
    dataset_metadata_document = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.related_metadata.title

    def generate_service_metadata(self, id: int):
        """ Creates a service metadata as xml, following the ISO19115 standard

        As a guide to this generator, you may read the ISO19115 workbook:
        ftp://ftp.ncddc.noaa.gov/pub/Metadata/Online_ISO_Training/Intro_to_ISO/workbooks/MI_Metadata.pdf

        Args:
            id (int): The metadata record id
        Returns:
            doc (str): The 'document' content
        """
        metadata = Metadata.objects.get(id=id)
        reduced_nsmap = {
            "gml": XML_NAMESPACES.get("gml", ""),
            "srv": XML_NAMESPACES.get("srv", ""),
            "gmd": XML_NAMESPACES.get("gmd", ""),
            "gco": XML_NAMESPACES.get("gco", ""),
            "xlink": XML_NAMESPACES.get("xlink", ""),
            None : XML_NAMESPACES.get("xsi", ""),
            "schemaLocation": "http://schemas.opengis.net/csw/2.0.2/profiles/apiso/1.0.0/apiso.xsd",
        }
        gmd = "{" + reduced_nsmap.get("gmd") + "}"
        xsi = "{" + reduced_nsmap.get(None) + "}"

        root = Element("{}MD_Metadata".format(gmd), nsmap=reduced_nsmap, attrib={"{}schemaLocation".format(xsi): reduced_nsmap.get("schemaLocation")})

        subs = OrderedDict()
        subs["{}fileIdentifier".format(gmd)] = self._create_file_identifier(metadata, reduced_nsmap)
        subs["{}language".format(gmd)] = self._create_language(metadata, reduced_nsmap)
        subs["{}characterSet".format(gmd)] = self._create_character_set(metadata, reduced_nsmap)
        subs["{}hierarchyLevel".format(gmd)] = self._create_hierarchy_level(metadata, reduced_nsmap)
        subs["{}hierarchyLevelName".format(gmd)] = self._create_hierarchy_level_name(metadata, reduced_nsmap)
        subs["{}contact".format(gmd)] = self._create_contact(metadata, reduced_nsmap)
        subs["{}dateStamp".format(gmd)] = self._create_date_stamp(metadata, reduced_nsmap)
        subs["{}metadataStandardName".format(gmd)] = self._create_metadata_standard_name(metadata, reduced_nsmap)
        subs["{}metadataStandardVersion".format(gmd)] = self._create_metadata_standard_version(metadata, reduced_nsmap)
        subs["{}identificationInfo".format(gmd)] = self._create_identification_info(metadata, reduced_nsmap)
        subs["{}distributionInfo".format(gmd)] = self._create_distribution_info(metadata, reduced_nsmap)
        subs["{}dataQualityInfo".format(gmd)] = self._create_data_quality_info(metadata, reduced_nsmap)

        for sub, func in subs.items():
            sub_element = xml_helper.create_subelement(root, sub)
            sub_element_content = func
            xml_helper.add_subelement(sub_element, sub_element_content)

        doc = etree.tostring(root, xml_declaration=True, encoding="utf-8")

        return doc

    def _create_file_identifier(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:fileIdentifier> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        ret_elem = Element("{" + reduced_nsmap.get("gco", "") + "}" + "CharacterString")
        ret_elem.text = metadata.uuid
        return ret_elem

    def _create_language(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:language> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        lang = "ger"  # ToDo: Create here something dynamic so we can provide international metadata as well
        code_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#LanguageCode"
        ret_elem = Element(
            "{" + reduced_nsmap.get("gmd", "") + "}" + "LanguageCode",
            attrib={
                "codeList": code_list,
                "codeListValue": lang,
            }
        )
        ret_elem.text = lang
        return ret_elem

    def _create_character_set(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:characterSet> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        char_set = "utf-8"
        char_set_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_CharacterSetCode"
        ret_elem = Element(
            "{" + reduced_nsmap.get("gmd", "") + "}" + "MD_CharacterSetCode",
            attrib={
                "codeList": char_set_list,
                "codeListValue": char_set,
            }
        )
        ret_elem.text = char_set
        return ret_elem

    def _create_hierarchy_level(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:hierarchyLevel> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        hierarchy_level = metadata.metadata_type.type
        hierarchy_level_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_ScopeCode"
        ret_elem = Element(
            "{" + reduced_nsmap.get("gmd", "") + "}" + "MD_ScopeCode",
            attrib={
                "codeList": hierarchy_level_list,
                "codeListValue": hierarchy_level,
            }
        )
        ret_elem.text = hierarchy_level
        return ret_elem

    def _create_hierarchy_level_name(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:hierarchyLevelName> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        service_type = metadata.service.servicetype.name
        if service_type == "wms":
            name = "Darstellungsdienst"  # ToDo: Find international solution for this
        else:
            name = "Downloadservice"  # ToDo: Find international solution for this

        ret_elem = Element("{" + reduced_nsmap.get("gco", "") + "}" + "CharacterString")
        ret_elem.text = name
        return ret_elem

    def _create_contact(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:CI_ResponsibleParty> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             resp_party_elem (_Element): The responsible party xml element
        """
        organization = metadata.contact

        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        resp_party_elem = Element(
            gmd + "CI_ResponsibleParty"
        )

        # gmd:individualName
        if organization.person_name is not None:
            indiv_name_elem = Element(
                gmd + "individualName"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.person_name
            xml_helper.add_subelement(indiv_name_elem, char_str_elem)
            xml_helper.add_subelement(resp_party_elem, indiv_name_elem)

        # gmd:organisationName
        if organization.organization_name is not None:
            org_name_elem = Element(
                gmd + "organisationName"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.organization_name
            xml_helper.add_subelement(org_name_elem, char_str_elem)
            xml_helper.add_subelement(resp_party_elem, org_name_elem)

        # gmd:positionName
        # ToDo: We do not persist the position of a person. Maybe this is required in the future, maybe never.
        # As long as we do not really use this, we fill this element as suggested in the iso19115 workbook, p. 45
        pos_name_elem = Element(
            gmd + "positionName",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        resp_party_elem.append(pos_name_elem)

        # gmd:contactInfo
        contact_info_elem = Element(
            gmd + "contactInfo"
        )
        contact_info_content_elem = self._create_contact_info_element(organization, metadata, reduced_nsmap)
        contact_info_elem.append(contact_info_content_elem)
        resp_party_elem.append(contact_info_elem)

        # gmd:role
        role_elem = Element(
            gmd + "role"
        )
        role_content_elem = self._create_role_element(organization, reduced_nsmap)
        role_elem.append(role_content_elem)
        resp_party_elem.append(role_elem)

        return resp_party_elem

    def _create_contact_info_element(self, organization: Organization, metadata:Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:CI_Contact> element with it's subelements

        Args:
            organization (Organization): The organization object which is used in here
            metadata (Metadata): The metadata object which is used in here
            reduced_nsmap (dict): The namespace map
        Returns:
             contact_elem (_Element): The contact information xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        contact_elem = Element(
            gmd + "CI_Contact"
        )

        # gmd:phone
        phone_elem = Element(
            gmd + "phone"
        )
        ci_phone_elem = Element(
            gmd + "CI_Telephone"
        )
        if organization.phone is not None:
            voice_elem = Element(
                gmd + "voice"
            )
            voice_char_str_elem = Element(
                gco + "CharacterString"
            )
            voice_char_str_elem.text = organization.phone

            voice_elem.append(voice_char_str_elem)
            ci_phone_elem.append(voice_elem)

        if organization.facsimile is not None:
            facsimile_elem = Element(
                gmd + "facsimile"
            )
            facs_char_str_elem = Element(
                gco + "CharacterString"
            )
            facs_char_str_elem.text = organization.facsimile

            facsimile_elem.append(facs_char_str_elem)
            ci_phone_elem.append(facsimile_elem)

        phone_elem.append(ci_phone_elem)
        contact_elem.append(phone_elem)

        address_ret_dict = self._create_address_element(organization, reduced_nsmap)
        address_elem = address_ret_dict["element"]
        num_address_subelements = address_ret_dict["num_subelements"]

        # only add the address element if we have at least one subelement inside
        if num_address_subelements > 0:
            contact_elem.append(address_elem)

        online_resource_elem = self._create_online_resource(metadata, reduced_nsmap)
        contact_elem.append(online_resource_elem)

        return contact_elem

    def _create_address_element(self, organization: Organization, reduced_nsmap: dict):
        """ Creates the <gmd:address> element with it's subelements

        Args:
            organization (Organization): The organization object which is used in here
            reduced_nsmap (dict): The namespace map
        Returns:
             dict: Contains 'element' and 'num_subelements'
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        # gmd:address
        address_elem = Element(
            gmd + "address"
        )
        ci_address_elem = Element(
            gmd + "CI_Address"
        )
        address_elem.append(ci_address_elem)
        address_elements = 0

        # gmd:address/../gmd:deliveryPoint
        if organization.address is not None:
            address_elements += 1
            tmp_elem = Element(
                gmd + "deliveryPoint"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.address
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../gmd:city
        if organization.city is not None:
            address_elements += 1
            tmp_elem = Element(
                gmd + "city"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.city
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../gmd:administrativeArea
        # ToDo: We are not doing this, since this information is not provided by the usual metadata

        # gmd:address/../gmd:postalCode
        if organization.postal_code is not None:
            address_elements += 1
            tmp_elem = Element(
                gmd + "postalCode"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.postal_code
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../gmd:country
        if organization.country is not None:
            address_elements += 1
            tmp_elem = Element(
                gmd + "country"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.country
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)

        # gmd:address/../gmd:electronicMailAddress
        if organization.email is not None:
            address_elements += 1
            tmp_elem = Element(
                gmd + "electronicMailAddress"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = organization.email
            tmp_elem.append(char_str_elem)
            ci_address_elem.append(tmp_elem)


        return {
            "element": address_elem,
            "num_subelements": address_elements,
        }

    def _create_online_resource(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:CI_OnlineResource> element with it's subelements

        Args:
            metadata (Metadata): The metadata object which is used in here
            reduced_nsmap (dict): The namespace map
        Returns:
             contact_elem (_Element): The contact information xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        resource_elem = Element(
            gmd + "onlineResource"
        )
        ci_resource_elem = Element(
            gmd + "CI_OnlineResource"
        )

        resource_elem.append(ci_resource_elem)

        # gmd:linkage
        linkage_elem = Element(
            gmd + "linkage"
        )
        tmp_elem = Element(
            gmd + "URL"
        )
        if metadata.inherit_proxy_uris:
            tmp_elem.text = HTTP_OR_SSL + HOST_NAME + "/service/capabilities/" + str(metadata.id)
        else:
            tmp_elem.text = metadata.capabilities_original_uri
        ci_resource_elem.append(linkage_elem)
        linkage_elem.append(tmp_elem)

        # gmd:protocol
        protocol_elem = Element(
            gmd + "protocol"
        )
        tmp_elem = Element(
            gmd + "CharacterString"
        )
        tmp_elem.text = "HTTP"
        ci_resource_elem.append(protocol_elem)
        protocol_elem.append(tmp_elem)

        # gmd:applicationProfile
        app_profile_elem = Element(
            gmd + "applicationProfile",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(app_profile_elem)

        # gmd:name
        name_elem = Element(
            gmd + "name"
        )
        tmp_elem = Element(
            gmd + "CharacterString"
        )
        tmp_elem.text = metadata.title
        ci_resource_elem.append(name_elem)
        name_elem.append(tmp_elem)

        # gmd:description
        descr_elem = Element(
            gmd + "description",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(descr_elem)

        # gmd:function
        func_elem = Element(
            gmd + "function",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_resource_elem.append(func_elem)

        return resource_elem

    def _create_role_element(self, organization, reduced_nsmap):
        """ Creates the <gmd:role> element

        Args:
            organization (Organization): The organization object which is used in here
            reduced_nsmap (dict): The namespace map
        Returns:
             ci_role_elem (_Element): The role information xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"

        val_list = "http://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml#CI_RoleCode"
        val = "pointOfContact"

        ci_role_elem = Element(
            gmd + "CI_RoleCode",
            attrib={
                "codeList": val_list,
                "codeListValue": val,
                "codeSpace": "007"
            }
        )
        ci_role_elem.text = val
        return ci_role_elem

    def _create_date_stamp(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:dateStamp> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(gco + "Date")

        if metadata.last_remote_change is not None:
            date = metadata.last_remote_change

        elif metadata.last_modified is not None:
            date = metadata.last_modified
        else:
            date = timezone.now()

        date = date.date().__str__()
        ret_elem.text = date

        return ret_elem

    def _create_metadata_standard_name(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:metadataStandardName> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gco + "CharacterString"
        )
        ret_elem.text = "ISO 19115 Geographic information - Metadata"

        return ret_elem

    def _create_metadata_standard_version(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:metadataStandardVersion> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gco + "CharacterString"
        )
        ret_elem.text = "ISO 19115:2003(E)"

        return ret_elem

    def _create_identification_info(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:identificationInfo> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        srv = "{" + reduced_nsmap.get("srv", "") + "}"
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            srv + "SV_ServiceIdentification"
        )

        # gmd:citation
        citation_elem = self._create_citation_elem(metadata, reduced_nsmap)
        ret_elem.append(citation_elem)

        # gmd:abstract
        abstract_elem = Element(
            gmd + "abstract"
        )
        char_str_elem = Element(
            gco + "CharacterString"
        )
        char_str_elem.text = metadata.abstract
        abstract_elem.append(char_str_elem)
        ret_elem.append(abstract_elem)

        # gmd:purpose
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # purpose_elem = Element(
        #     gmd + "purpose"
        # )

        # gmd:credit
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # credit_elem = Element(
        #     gmd + "credit"
        # )

        # gmd:status
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # status_elem = Element(
        #     gmd + "status"
        # )

        # gmd:pointOfContact
        point_of_contact_elem = Element(
            gmd + "pointOfContact"
        )
        point_of_contact_content_elem = self._create_contact(metadata, reduced_nsmap)
        point_of_contact_elem.append(point_of_contact_content_elem)
        ret_elem.append(point_of_contact_elem)

        # gmd:resourceMaintenance
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # resource_maintenance_elem = Element(
        #     gmd + "resourceMaintenance"
        # )

        # gmd:graphicOverview
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # graphic_overview_elem = Element(
        #     gmd + "graphicOverview"
        # )

        # gmd:resourceFormat
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # resource_format_elem = Element(
        #     gmd + "resourceFormat"
        # )

        # gmd:descriptiveKeywords
        descr_keywords_elem = Element(
            gmd + "descriptiveKeywords"
        )
        descr_keywords_content_elem = self._create_keywords(metadata, reduced_nsmap)
        descr_keywords_elem.append(descr_keywords_content_elem)
        ret_elem.append(descr_keywords_elem)

        # gmd:resourceSpecificUsage
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # res_specific_usage_elem = Element(
        #     gmd + "resourceSpecificUsage"
        # )

        # gmd:resourceConstraints
        res_constraints_elem = Element(
            gmd + "resourceConstraints"
        )
        res_constraints_content_elem = self._create_legal_constraints(metadata, reduced_nsmap)
        res_constraints_elem.append(res_constraints_content_elem)
        ret_elem.append(res_constraints_elem)

        # gmd:aggregationInfo
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # aggregation_info_elem = Element(
        #     gmd + "aggregationInfo"
        # )

        # gmd:serviceType
        service_type_elem = Element(
            srv + "serviceType",
        )
        locale_name_elem = Element(
            gco + "LocalName"
        )
        # resolve service type according to best practice
        service_type = metadata.service.servicetype.name
        if service_type == 'wms':
            service_type = "WebMapService"
        elif service_type == 'wfs':
            service_type = "WebFeatureService"
        else:
            service_type = "unknown"
        service_type_version = metadata.service.servicetype.version
        locale_name_elem.text = "urn:ogc:serviceType:{}:{}".format(service_type, service_type_version)
        service_type_elem.append(locale_name_elem)
        ret_elem.append(service_type_elem)

        # gmd:serviceTypeVersion
        service_version_elem = Element(
            srv + "serviceTypeVersion",
        )
        char_str_elem = Element(
            gco + "CharacterString"
        )
        char_str_elem.text = service_type_version
        service_version_elem.append(char_str_elem)
        ret_elem.append(service_version_elem)

        # gmd:accessProperties
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # access_properties_elem = Element(
        #     gmd + "accessProperties"
        # )

        # gmd:restrictions
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # restrictions_elem = Element(
        #     gmd + "restrictions"
        # )

        # gmd:keywords
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # keywords_elem = Element(
        #     gmd + "keywords"
        # )

        # gmd:extent
        extent_elem = Element(
            srv + "extent"
        )
        extent_content_elem = self._create_extent(metadata, reduced_nsmap)
        extent_elem.append(extent_content_elem)
        ret_elem.append(extent_elem)

        # gmd:couplingType
        coupling_type_elem = Element(
            srv + "couplingType",
        )
        coupling_type_content_elem = Element(
            srv + "SV_CouplingType",
            attrib={
                "codeList": "SV_CouplingType",
                "codeListValue": "tight"
            }
        )
        coupling_type_elem.append(coupling_type_content_elem)
        ret_elem.append(coupling_type_elem)

        # gmd:coupledResource
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # coupled_res_elem = Element(
        #     gmd + "coupledResource"
        # )

        # gmd:containsOperations
        contains_op_elem = Element(
            srv + "containsOperations"
        )
        contains_op_content_elem = self._create_operation_metadata(metadata, reduced_nsmap)
        contains_op_elem.append(contains_op_content_elem)
        ret_elem.append(contains_op_elem)

        # gmd:operatesOn
        # NOTE: We do not use this so far, but keep this in the code as a preparation for one day
        # operates_on_elem = Element(
        #     gmd + "operatesOn"
        # )

        return ret_elem

    def _create_citation_elem(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:citation> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "citation"
        )
        ci_citation_elem = Element(
            gmd + "CI_Citation"
        )
        ret_elem.append(ci_citation_elem)

        # gmd:title
        title_elem = Element(
            gmd + "title"
        )
        title_elem.text = metadata.title
        ci_citation_elem.append(title_elem)

        # gmd:alternateTitle
        alt_title_elem = Element(
            gmd + "alternateTitle",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(alt_title_elem)

        # gmd:date
        date_elem = self._create_date_stamp(metadata, reduced_nsmap)
        ci_citation_elem.append(date_elem)

        # gmd:edition
        edition_elem = Element(
            gmd + "edition",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(edition_elem)

        # gmd:editionDate
        edition_date_elem = Element(
            gmd + "editionDate",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(edition_date_elem)

        # gmd:identifier
        identifier_elem = Element(
            gmd + "identifier"
        )
        identifier_elem.text = metadata.identifier
        ci_citation_elem.append(identifier_elem)

        # gmd:citedResponsibleParty
        cited_resp_party_elem = Element(
            gmd + "citedResponsibleParty"
        )
        cited_resp_party_content_elem = self._create_contact(metadata, reduced_nsmap)
        cited_resp_party_elem.append(cited_resp_party_content_elem)
        ci_citation_elem.append(cited_resp_party_elem)

        # gmd:presentationForm
        presentation_form_elem = Element(
            gmd + "presentationForm",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(presentation_form_elem)

        # gmd:series
        series_elem = Element(
            gmd + "series",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(series_elem)

        # gmd:otherCitationDetails
        cit_details_elem = Element(
            gmd + "otherCitationDetails",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(cit_details_elem)

        # gmd:collectiveTitle
        collective_title_elem = Element(
            gmd + "collectiveTitle",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(collective_title_elem)

        # gmd:ISBN
        isbn_elem = Element(
            gmd + "ISBN",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(isbn_elem)

        # gmd:ISSN
        issn_elem = Element(
            gmd + "ISSN",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ci_citation_elem.append(issn_elem)

        return ret_elem

    def _create_keywords(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:MD_Keywords> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_Keywords"
        )

        keywords = metadata.keywords.all()
        for keyword in keywords:
            keyword_elem = Element(
                gmd + "keyword"
            )
            char_str_elem = Element(
                gco + "CharacterString"
            )
            char_str_elem.text = keyword.keyword
            keyword_elem.append(char_str_elem)
            ret_elem.append(keyword_elem)

        return ret_elem

    def _create_legal_constraints(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:MD_LegalConstraints> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_LegalConstraints"
        )

        # gmd:useLimitation
        use_limitation_elem = Element(
            gmd + "useLimitation",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(use_limitation_elem)

        # gmd:accessConstraints
        access_constraints_elem = Element(
            gmd + "accessConstraints",
        )
        code_list = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/ML_gmxCodelists.xml#MD_RestrictionCode"
        code_list_val = "otherRestrictions"
        md_restr_code_elem = Element(
            gmd + "MD_RestrictionCode",
            attrib={
                "codeList": code_list,
                "codeListValue": code_list_val,
            }
        )
        md_restr_code_elem.text = code_list_val
        access_constraints_elem.append(md_restr_code_elem)
        ret_elem.append(access_constraints_elem)

        # gmd:otherConstraints
        other_constraints_elem = Element(
            gmd + "otherConstraints",
        )
        char_str_elem = Element(
            gco + "CharacterString"
        )
        constraints_text = "no constraints"
        if metadata.access_constraints is not None and len(metadata.access_constraints) > 0:
            constraints_text = metadata.access_constraints
        char_str_elem.text = constraints_text
        other_constraints_elem.append(char_str_elem)
        ret_elem.append(other_constraints_elem)

        return ret_elem

    def _create_extent(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:EX_Extent> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "EX_Extent"
        )

        # gmd:description
        descr_elem = Element(
            gmd + "description",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(descr_elem)

        # gmd:geographicElement
        geographic_elem = Element(
            gmd + "geographicElement"
        )
        geographic_content_elem = self._create_bounding_box(metadata, reduced_nsmap)
        geographic_elem.append(geographic_content_elem)
        ret_elem.append(geographic_elem)

        # gmd:temporalElement
        temp_elem = Element(
            gmd + "temporalElement",
            attrib={
                gco + "nilReason": "unknown"
            }
        )

        # gmd:verticalElement
        vertical_elem = Element(
            gmd + "verticalElement",
            attrib={
                gco + "nilReason": "unknown"
            }
        )

        return ret_elem

    def _create_bounding_box(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:EX_GeographicBoundingBox> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        bbox = metadata.bounding_geometry
        if bbox is None:
            bbox = metadata.find_max_bounding_box()
        extent = bbox.extent

        ret_elem = Element(
            gmd + "EX_GeographicBoundingBox"
        )

        # gmd:extentTypeCode
        extent_type_code_elem = Element(
            gmd + "extentTypeCode",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(extent_type_code_elem)

        # gmd:westBoundingLongitude
        west_bound_elem = Element(
            gmd + "westBoundLongitude"
        )
        decimal_elem = Element(
            gco + "Decimal"
        )
        decimal_elem.text = str(extent[0])
        west_bound_elem.append(decimal_elem)
        ret_elem.append(west_bound_elem)

        # gmd:eastBoundingLongitude
        east_bound_elem = Element(
            gmd + "eastBoundLongitude"
        )
        decimal_elem = Element(
            gco + "Decimal"
        )
        decimal_elem.text = str(extent[2])
        east_bound_elem.append(decimal_elem)
        ret_elem.append(east_bound_elem)

        # gmd:southBoundingLongitude
        south_bound_elem = Element(
            gmd + "southBoundLatitude"
        )
        decimal_elem = Element(
            gco + "Decimal"
        )
        decimal_elem.text = str(extent[1])
        south_bound_elem.append(decimal_elem)
        ret_elem.append(south_bound_elem)

        # gmd:northBoundingLongitude
        north_bound_elem = Element(
            gmd + "northBoundLatitude"
        )
        decimal_elem = Element(
            gco + "Decimal"
        )
        decimal_elem.text = str(extent[3])
        north_bound_elem.append(decimal_elem)
        ret_elem.append(north_bound_elem)

        return ret_elem

    def _create_operation_metadata(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:SV_OperationMetadata> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"
        srv = "{" + reduced_nsmap.get("srv", "") + "}"

        ret_elem = Element(
            srv + "SV_OperationMetadata"
        )

        # srv:operationName
        operation_name_elem = Element(
            srv + "operationName"
        )
        char_str_elem = Element(
            gco + "CharacterString"
        )
        char_str_elem.text = "GetCapabilities"
        operation_name_elem.append(char_str_elem)
        ret_elem.append(operation_name_elem)

        # srv:DCP
        dcp_elem = Element(
            srv + "DCP"
        )
        dcp_list_elem = Element(
            srv + "DCPList",
            attrib={
                "codeList": "DCPList",
                "codeListValue": "WebService",
            }
        )
        dcp_elem.append(dcp_list_elem)
        ret_elem.append(dcp_elem)

        # srv:operationDescription
        operation_descr_elem = Element(
            srv + "operationDescription"
        )
        char_str_elem = Element(
            gco + "CharacterString"
        )
        char_str_elem.text = "Request the service capabilities document"
        operation_descr_elem.append(char_str_elem)
        ret_elem.append(operation_descr_elem)

        # srv:invocationName
        invocation_name_elem = Element(
            srv + "invocationName",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(invocation_name_elem)

        # srv:parameters
        parameters_elem = Element(
            srv + "parameters",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(parameters_elem)

        # srv:connectPoint
        connect_point_elem = Element(
            srv + "connectPoint"
        )
        connect_point_elem.append(self._create_online_resource(metadata, reduced_nsmap))
        ret_elem.append(connect_point_elem)

        # srv:dependsOn
        depends_on_elem = Element(
            srv + "dependsOn",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(depends_on_elem)

        return ret_elem

    def _create_distribution_info(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:distributionInfo> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_Distribution"
        )

        # gmd:distributionFormat
        distr_format_elem = Element(
            gmd + "distributionFormat"
        )
        distr_format_content_elem = self._create_distribution_format(metadata, reduced_nsmap)
        distr_format_elem.append(distr_format_content_elem)
        ret_elem.append(distr_format_elem)

        # gmd:distributor
        distributor_elem = Element(
            gmd + "distributor"
        )
        distributor_content_elem = self._create_distributor(metadata, reduced_nsmap)
        distributor_elem.append(distributor_content_elem)
        ret_elem.append(distributor_elem)

        # gmd:transferOptions
        transfer_options_elem = Element(
            gmd + "transferOptions"
        )

        return ret_elem

    def _create_distribution_format(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:MD_Format> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_Format",
        )

        # gmd:name
        name_elem = Element(
            gmd + "name",
            attrib={
                gco + "nilReason": "inapplicable"
            }
        )
        ret_elem.append(name_elem)

        # gmd:version
        version_elem = Element(
            gmd + "version",
            attrib={
                gco + "nilReason": "inapplicable"
            }
        )
        ret_elem.append(version_elem)

        return ret_elem

    def _create_distributor(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:MD_Distributor> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_Distributor"
        )

        # gmd:distributorContact
        distributor_contact_elem = Element(
            gmd + "distributorContact"
        )
        distributor_contact_elem.append(self._create_contact(metadata, reduced_nsmap))
        ret_elem.append(distributor_contact_elem)

        # gmd:distributionOrderProcess
        distribution_order_elem = Element(
            gmd + "distributionOrderProcess",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(distribution_order_elem)

        # gmd:distributorFormat
        distributor_format_elem = Element(
            gmd + "distributorFormat",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(distributor_format_elem)

        # gmd:distributorTransferOptions
        distributor_transfer_options_elem = Element(
            gmd + "distributorTransferOptions",
        )
        distributor_transfer_options_elem.append(self._create_digital_transfer_options(metadata, reduced_nsmap))

        ret_elem.append(distributor_transfer_options_elem)

        return ret_elem

    def _create_digital_transfer_options(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:MD_DigitalTransferOptions> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "MD_DigitalTransferOptions"
        )

        # gmd:unitsOfDistribution
        units_of_distribution_elem = Element(
            gmd + "unitsOfDistribution",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(units_of_distribution_elem)

        # gmd:transferSize
        transfer_size_elem = Element(
            gmd + "transferSize",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(transfer_size_elem)

        # gmd:onLine
        online_elem = Element(
            gmd + "onLine",
        )
        online_elem.append(self._create_online_resource(metadata, reduced_nsmap))
        ret_elem.append(online_elem)

        # gmd:offLine
        offline_elem = Element(
            gmd + "offLine",
            attrib={
                gco + "nilReason": "unknown"
            }
        )
        ret_elem.append(offline_elem)

        return ret_elem

    def _create_data_quality_info(self, metadata: Metadata, reduced_nsmap):
        """ Creates the <gmd:dataQualityInfo> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "DQ_DataQuality"
        )

        # gmd:scope
        scope_elem = Element(
            gmd + "scope"
        )
        scope_elem.append(self._create_scope(metadata, reduced_nsmap))
        ret_elem.append(scope_elem)

        # gmd:report
        report_elem = Element(
            gmd + "report"
        )
        ret_elem.append(report_elem)

        # gmd:lineage
        lineage_elem = Element(
            gmd + "lineage"
        )
        ret_elem.append(lineage_elem)

        return ret_elem

    def _create_scope(self, metadata: Metadata, reduced_nsmap: dict):
        """ Creates the <gmd:DQ_Scope> element

        Args:
            metadata (Metadata): The metadata element, which carries the needed information
            reduced_nsmap (dict):  The namespace map
        Returns:
             ret_elem (_Element): The requested xml element
        """
        gmd = "{" + reduced_nsmap.get("gmd", "") + "}"
        gco = "{" + reduced_nsmap.get("gco", "") + "}"

        ret_elem = Element(
            gmd + "DQ_Scope"
        )

        # gmd:level
        level_elem = Element(
            gmd + "level"
        )
        level_elem.append(self._create_hierarchy_level(metadata, reduced_nsmap))
        ret_elem.append(level_elem)

        # gmd:extent
        extent_elem = Element(
            gmd + "extent"
        )
        extent_elem.append(self._create_extent(metadata, reduced_nsmap))
        ret_elem.append(extent_elem)

        # gmd:levelDescription
        level_description_elem = Element(
            gmd + "levelDescription",
            attrib={
                gco + "nilReason": "unknown",
            }
        )
        ret_elem.append(level_description_elem)

        return ret_elem


    def restore(self):
        """ We overwrite the current metadata xml with the original

        Returns:
             nothing
        """
        self.current_capability_document = self.original_capability_document
        self.save()

    def restore_subelement(self, identifier: str):
        """ Restores only the layer which matches the provided identifier

        Args:
            identifier (str): The identifier which matches a single layer in the document
        Returns:
             nothing
        """
        # only restored the layer and it's children
        cap_doc_curr_obj = xml_helper.parse_xml(self.current_capability_document)
        cap_doc_orig_obj = xml_helper.parse_xml(self.original_capability_document)

        xml_layer_obj_curr = xml_helper.find_element_where_text(cap_doc_curr_obj, identifier)[0]
        xml_layer_obj_orig = xml_helper.find_element_where_text(cap_doc_orig_obj, identifier)[0]

        # find position where original element existed
        parent_orig = xml_helper.get_parent(xml_layer_obj_orig)
        orig_index = parent_orig.index(xml_layer_obj_orig)

        # insert original element at the original index and remove current element (which now is at index + 1)
        parent_curr = xml_helper.get_parent(xml_layer_obj_curr)
        parent_curr.insert(orig_index, xml_layer_obj_orig)
        parent_curr.remove(xml_layer_obj_curr)

        self.current_capability_document = xml_helper.xml_to_string(cap_doc_curr_obj)
        self.save()


class TermsOfUse(Resource):
    name = models.CharField(max_length=100)
    symbol_url = models.CharField(max_length=100)
    description = models.TextField()
    is_open_data = models.BooleanField(default=False)
    fees = models.CharField(max_length=100)


class CategoryOrigin(models.Model):
    name = models.CharField(max_length=255)
    uri = models.CharField(max_length=500)

    def __str__(self):
        return self.name


class Category(Resource):
    type = models.CharField(max_length=255)
    title_locale_1 = models.CharField(max_length=255, null=True)
    title_locale_2 = models.CharField(max_length=255, null=True)
    title_EN = models.CharField(max_length=255, null=True)
    description_locale_1 = models.TextField(null=True)
    description_locale_2 = models.TextField(null=True)
    description_EN = models.TextField(null=True)
    symbol = models.CharField(max_length=500, null=True)
    online_link = models.CharField(max_length=500, null=True)
    origin = models.ForeignKey(CategoryOrigin, on_delete=models.DO_NOTHING, null=True)

    def __str__(self):
        return self.title_EN + " (" + self.type + ")"


class ServiceType(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    specification = models.URLField(blank=False, null=True)

    def __str__(self):
        return self.name


class Service(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="service")
    parent_service = models.ForeignKey('self', on_delete=models.CASCADE, related_name="child_service", null=True, default=None, blank=True)
    published_for = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, related_name="published_for", null=True, default=None, blank=True)
    servicetype = models.ForeignKey(ServiceType, on_delete=models.DO_NOTHING, blank=True)
    categories = models.ManyToManyField(Category, blank=True)
    is_root = models.BooleanField(default=False)
    availability = models.DecimalField(decimal_places=2, max_digits=4, default=0.0)
    is_available = models.BooleanField(default=False)
    get_capabilities_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_map_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_feature_info_uri = models.CharField(max_length=1000, null=True, blank=True)
    describe_layer_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_legend_graphic_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_styles_uri = models.CharField(max_length=1000, null=True, blank=True)
    formats = models.ManyToManyField('MimeType', blank=True)

    # used to store ows linked_service_metadata until parsing
    # will not be part of the db
    linked_service_metadata = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.root_layer = None
        self.feature_type_list = []
        self.formats_list = []
        self.categories_list = []

    def __str__(self):
        return str(self.id)

    @transaction.atomic
    def delete_child_data(self, child):
        """ Delete all layer data like related iso metadata

        Args:
            layer (Layer): The current layer object
        Returns:
            nothing
        """
        # remove related metadata
        iso_mds = MetadataRelation.objects.filter(metadata_from=child.metadata)
        for iso_md in iso_mds:
            md_2 = iso_md.metadata_to
            md_2.delete()
            iso_md.delete()
        if isinstance(child, FeatureType):
            # no other way to remove feature type metadata on service deleting
            child.metadata.delete()
        child.delete()

    @transaction.atomic
    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete method

        Recursively remove children

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove related metadata
        linked_mds = MetadataRelation.objects.filter(metadata_from=self.metadata)
        for linked_md in linked_mds:
            md_2 = linked_md.metadata_to
            md_2.delete()
            linked_md.delete()

        # remove subelements
        if self.servicetype.name == 'wms':
            layers = self.child_service.all()
            for layer in layers:
                self.delete_child_data(layer)
        elif self.servicetype.name == 'wfs':
            feature_types = self.featuretypes.all()
            for f_t in feature_types:
                self.delete_child_data(f_t)
        self.metadata.delete()
        super().delete()

    def __get_children(self, current, layers: list):
        """ Recursive appending of all layers

        Args:
            current (Layer): The current layer instance
            layers (list): The list of all collected layers so far
        Returns:
             nothing
        """
        layers.append(current)
        for layer in current.children_list:
            layers.append(layer)
            if len(layer.children_list) > 0:
                self.__get_children(layer, layers)

    def get_all_layers(self):
        """ Returns all layers in a list that can be found in this service

        NOTE: THIS IS ONLY USED FOR CHILDREN_LIST, WHICH SHOULD ONLY BE USED FOR NON-PERSISTED OBJECTS!!!

        Returns:
             layers (list): The layers
        """

        layers = []
        self.__get_children(self.root_layer, layers)
        return layers

    def activate_service(self, is_active: bool):
        """ Toggles the activity status of a service and it's metadata

        Args:
            is_active (bool): Whether the service shall be activated or not
        Returns:
             nothing
        """
        self.is_active = is_active
        self.metadata.is_active = is_active

        linked_mds = self.metadata.related_metadata.all()
        for md_relation in linked_mds:
            md_relation.metadata_to.is_active = is_active
            md_relation.metadata_to.save()

        self.metadata.save()
        self.save()


class Layer(Service):
    class Meta:
        ordering = ["position"]
    identifier = models.CharField(max_length=500, null=True)
    hits = models.IntegerField(default=0)
    preview_image = models.CharField(max_length=100, blank=True, null=True)
    preview_extent = models.CharField(max_length=100, blank=True, null=True)
    preview_legend = models.CharField(max_length=100)
    parent_layer = models.ForeignKey("self", on_delete=models.CASCADE, null=True, related_name="child_layer")
    position = models.IntegerField(default=0)
    is_queryable = models.BooleanField(default=False)
    is_opaque = models.BooleanField(default=False)
    is_cascaded = models.BooleanField(default=False)
    scale_min = models.FloatField(default=0)
    scale_max = models.FloatField(default=0)
    bbox_lat_lon = models.PolygonField(default=Polygon(
        (
            (-90.0, -180.0),
            (-90.0, 180.0),
            (90.0, 180.0),
            (90.0, -180.0),
            (-90.0, -180.0),
        )
    ))
    iso_metadata = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.children_list = []
        self.dimension = None

    def __str__(self):
        return str(self.identifier)

    def activate_layer_recursive(self, new_status):
        """ Walk recursive through all layers of a wms and set the activity status new

        Args:
            root_layer: The root layer, where the recursion begins
            new_status: The new status that will be persisted
        Returns:
             nothing
        """
        self.metadata.is_active = new_status
        self.metadata.save()
        self.save()

        # check for all related metadata, we need to toggle their active status as well
        rel_md = self.metadata.related_metadata.all()
        for md in rel_md:
            dependencies = MetadataRelation.objects.filter(
                metadata_to=md.metadata_to,
                metadata_from__is_active=True,
            )
            if dependencies.count() >= 1 and md not in dependencies:
                # we still have multiple dependencies on this relation (besides us), we can not deactivate the metadata
                pass
            else:
                # since we have no more dependencies on this metadata, we can set it inactive
                md.metadata_to.is_active = new_status
                md.metadata_to.save()
                md.save()

        for layer in self.child_layer.all():
            layer.activate_layer_recursive(new_status)


class Module(Service):
    type = models.CharField(max_length=100)

    def __str__(self):
        return self.type


class ReferenceSystem(models.Model):
    code = models.CharField(max_length=100)
    prefix = models.CharField(max_length=255, default="EPSG:")
    version = models.CharField(max_length=50, default="9.6.1")

    def __str__(self):
        return self.code


class Dataset(Resource):
    time_begin = models.DateTimeField()
    time_end = models.DateTimeField()


class MimeType(Resource):
    action = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=500)

    def __str__(self):
        return self.mime_type


class Dimension(models.Model):
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    units = models.CharField(max_length=255)
    default = models.CharField(max_length=255)
    nearest_value = models.CharField(max_length=255)
    current = models.CharField(max_length=255)
    extent = models.CharField(max_length=500)
    inherited = models.BooleanField()

    def __str__(self):
        return self.layer.name + ": " + self.name


class Style(models.Model):
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    uri = models.CharField(max_length=500)
    height = models.IntegerField()
    width = models.IntegerField()
    mime_type = models.CharField(max_length=500)

    def __str__(self):
        return self.layer.name + ": " + self.name


class FeatureType(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="featuretype")
    service = models.ForeignKey(Service, null=True,  blank=True, on_delete=models.CASCADE, related_name="featuretypes")
    is_searchable = models.BooleanField(default=False)
    default_srs = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING, null=True, related_name="default_srs")
    inspire_download = models.BooleanField(default=False)
    bbox_lat_lon = models.PolygonField(default=Polygon(
        (
            (-90.0, -180.0),
            (-90.0, 180.0),
            (90.0, 180.0),
            (90.0, -180.0),
            (-90.0, -180.0),
        )
    ))
    formats = models.ManyToManyField(MimeType)
    elements = models.ManyToManyField('FeatureTypeElement')
    namespaces = models.ManyToManyField('Namespace')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.additional_srs_list = []
        self.keywords_list = []
        self.formats_list = []
        self.elements_list = []
        self.namespaces_list = []
        self.dataset_md_list = []

    def __str__(self):
        return self.metadata.identifier

    def restore(self):
        """ Reset the metadata to it's original capabilities content

        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper
        if self.service is None:
            return
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        if self.service.servicetype.name == ServiceTypes.WFS.value:
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.service.metadata.capabilities_original_uri)
        if service is None:
            return
        service.get_capabilities()
        service.get_single_feature_type_metadata(self.metadata.identifier)
        result = service.feature_type_list.get(self.metadata.identifier, {})
        original_ft = result.get("feature_type")
        keywords = result.get("keyword_list")

        # now restore the "metadata"
        self.title = original_ft.title
        self.abstract = original_ft.abstract
        self.metadata.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.metadata.keywords.add(keyword)
        self.is_custom = False


class FeatureTypeElement(Resource):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name


class Namespace(models.Model):
    name = models.CharField(max_length=50)
    version = models.CharField(max_length=50, blank=True, null=True)
    uri = models.CharField(max_length=500)

    def __str__(self):
        return self.name + " (" + self.uri + ")"
