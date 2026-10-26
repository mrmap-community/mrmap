""" Tests for the metadata references which MrMap publishes in its capabilities xml.

    MrMap publishes two kinds of metadata references for a layer / feature type: the
    links which were imported with the capabilities document (`remote_metadata`) and
    the curated links a curator added in MrMap (`MetadataRelation`). Which relations
    are published is decided by the coupling policy, see
    registry/querys/metadata.py.

    The capabilities of the fixture services are rendered without a running service:
    the persisted xml backup file is the base of the rendering, see
    registry.models.document.CapabilitiesDocumentModelMixin.get_updated_capabilitites.
"""

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag

from lxml import etree

from MrMap.settings import BASE_DIR
from registry.enums.metadata import (MetadataOriginEnum,
                                     MetadataRelationPublicationEnum)
from registry.mappers.parsers.metadata_links import (METADATA_URL_FORMAT,
                                                     METADATA_URL_TYPE,
                                                     PublishedMetadataLink,
                                                     serialize_wms_metadata_url)
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata, MetadataRelation,
                                      ServiceMetadataRecord)
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from tests.django.contrib import XpathTestCase

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

WMS_CAPABILITIES = f"{BASE_DIR}/tests/django/test_data/capabilities/wms/fixture_1.3.0.xml"
WFS_CAPABILITIES = f"{BASE_DIR}/tests/django/test_data/capabilities/wfs/fixture_2.0.0.xml"

WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WFS_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

FIXTURE_DATASET = "de.dwd.geoserver.fach.RBSN_RR"
SECOND_FIXTURE_DATASET = "de.dwd.geoserver.fach.RBSN_RH"

# The elements the wms schema defines after a MetadataURL element, see
# https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd and the wms 1.1.1 dtd.
WMS_FOLLOWERS = ("DataURL", "FeatureListURL", "Style", "ScaleHint",
                 "MinScaleDenominator", "MaxScaleDenominator", "Layer")

# lxml evaluates xpath 1.0 which does not know sequences, so every follower needs its
# own comparison.
WMS_FOLLOWER_PREDICATE = " or ".join(
    f"local-name()='{follower}'" for follower in WMS_FOLLOWERS)


@tag("registry", "models", "mappers")
class PublishedMetadataLinksTest(XpathTestCase):
    """ Tests the MetadataURL elements of the rendered capabilities documents. """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_wms.json", "test_wfs.json",
                "test_datasetmetadata.json"]

    def setUp(self):
        self.wms = self._store_document(WebMapService, WMS_PK, WMS_CAPABILITIES)
        self.wfs = self._store_document(WebFeatureService, WFS_PK, WFS_CAPABILITIES)
        self.dataset = DatasetMetadataRecord.objects.get(
            file_identifier=FIXTURE_DATASET)
        self.other_dataset = DatasetMetadataRecord.objects.get(
            file_identifier=SECOND_FIXTURE_DATASET)

    @staticmethod
    def _store_document(model, pk, path, document=None):
        """ Store the given capabilities document as xml backup of the service. """
        service = model.objects.get(pk=pk)
        if document is None:
            with open(path, mode="rb") as cap_file:
                document = cap_file.read()
        else:
            document = etree.tostring(document, xml_declaration=True, encoding="UTF-8")
        service.xml_backup_file = SimpleUploadedFile("capabilitites.xml", document)
        service.save()
        return service

    @staticmethod
    def _wms_document():
        """ Return the parsed capabilities document of the fixture wms. """
        with open(WMS_CAPABILITIES, mode="rb") as cap_file:
            return etree.parse(cap_file)

    def _curated_relation(self, dataset=None, **resource):
        """ Create a relation which a curator added in MrMap. """
        return MetadataRelation.objects.create(
            dataset_metadata=dataset or self.dataset,
            is_internal=True,
            origin=MetadataOriginEnum.EDITOR.value,
            **resource)

    def _render_wms(self):
        """ Render the capabilities of the fixture wms out of the database. """
        return WebMapService.objects.prefetch_whole_service().get(
            pk=self.wms.pk).get_updated_capabilitites()

    def _render_wfs(self):
        """ Render the capabilities of the fixture wfs out of the database. """
        return WebFeatureService.objects.prefetch_whole_service().get(
            pk=self.wfs.pk).get_updated_capabilitites()

    def _layer(self, identifier):
        return Layer.objects.get(service=self.wms, identifier=identifier)

    def _feature_type(self, identifier):
        return FeatureType.objects.get(service=self.wfs, identifier=identifier)

    def _wms_metadata_urls(self, capabilities, identifier):
        return self._get_by_xpath(
            capabilities,
            f"//d:Capability//d:Layer[d:Name='{identifier}']/d:MetadataURL")

    def _wfs_metadata_urls(self, capabilities, identifier):
        return self._get_by_xpath(
            capabilities,
            f"//wfs:FeatureTypeList//wfs:FeatureType[wfs:Name='{identifier}']"
            f"/wfs:MetadataURL")

    @staticmethod
    def _wms_link(metadata_url):
        """ Return the link a wms metadata reference points to.

            A wms reference holds the link in its OnlineResource child, it is None if
            the reference does not point anywhere.
        """
        for child in metadata_url.iterchildren():
            if etree.QName(child).localname == "OnlineResource":
                return child.get(XLINK_HREF)
        return None

    def assertWmsMetadataUrls(self, capabilities, identifier, expected_links):
        """ Assert that the layer publishes exactly the given references.

            Every reference must be a child of the layer, must hold a Format and an
            OnlineResource in the order the schema defines and must not be placed
            after one of the elements which the schema defines after a MetadataURL.
        """
        metadata_urls = self._wms_metadata_urls(capabilities, identifier)
        self.assertEqual(
            [self._wms_link(url) for url in metadata_urls], expected_links,
            f"unexpected metadata references published for layer {identifier}")

        for metadata_url in metadata_urls:
            self.assertEqual(
                [etree.QName(child).localname for child in metadata_url],
                ["Format", "OnlineResource"])

        # no reference of another element than a layer
        self.assertXpathCount(
            capabilities,
            "//d:Capability//*[local-name()='MetadataURL']"
            "[not(parent::*[local-name()='Layer'])]", 0)
        # every reference sits in front of all elements which must follow it
        self.assertXpathCount(
            capabilities,
            f"//d:Capability//d:Layer[d:Name='{identifier}']"
            f"/*[local-name()='MetadataURL']"
            f"[preceding-sibling::*[{WMS_FOLLOWER_PREDICATE}]]", 0)
        return metadata_urls

    def test_curated_relation_is_published(self):
        """ A relation a curator added publishes the linked dataset record. """
        layer = self._layer("node1.1.1")
        self._curated_relation(layer=layer)

        capabilities = self._render_wms()

        metadata_urls = self.assertWmsMetadataUrls(
            capabilities, "node1.1.1", [self.dataset.origin_url])
        self.assertEqual(metadata_urls[0].get("type"), METADATA_URL_TYPE)
        self.assertEqual(metadata_urls[0][0].text, METADATA_URL_FORMAT)

    def test_curated_relation_is_published_in_front_of_child_layers(self):
        """ A published reference keeps the position the schema defines for it. """
        layer = self._layer("node1.1")
        self._curated_relation(dataset=self.other_dataset, layer=layer)

        capabilities = self._render_wms()

        self.assertXpathCount(
            capabilities,
            "//d:Capability//d:Layer[d:Name='node1.1']/d:Layer", 3)
        self.assertWmsMetadataUrls(
            capabilities, "node1.1", [self.other_dataset.origin_url])

    def _document_with_metadata_url(self, identifier, link=None,
                                    metadata_type="FGDC"):
        """ Return the wms document of the fixtures with an extra metadata reference.

            A reference without link is not valid, it is the way MrMap used to leave
            behind a reference which lost its link.
        """
        namespace = "http://www.opengis.net/wms"
        document = self._wms_document()
        layer = document.getroot().xpath(
            f"//d:Capability//d:Layer[d:Name='{identifier}']",
            namespaces={"d": namespace})[0]
        metadata_url = etree.SubElement(
            layer, f"{{{namespace}}}MetadataURL", {"type": metadata_type})
        etree.SubElement(
            metadata_url, f"{{{namespace}}}Format").text = METADATA_URL_FORMAT
        if link:
            etree.SubElement(
                metadata_url, f"{{{namespace}}}OnlineResource").set(XLINK_HREF, link)
        return document

    def test_imported_metadata_url_is_preserved_and_not_replaced(self):
        """ An imported reference keeps the information of the source document. """
        imported_link = "https://registry.example.com/id/de.example/imported"
        self._store_document(
            WebMapService, WMS_PK, WMS_CAPABILITIES,
            document=self._document_with_metadata_url(
                "node1.1.2", link=imported_link))
        layer = self._layer("node1.1.2")
        LayerRemoteMetadata.objects.create(describes=layer, link=imported_link)

        capabilities = self._render_wms()

        metadata_urls = self.assertWmsMetadataUrls(
            capabilities, "node1.1.2", [imported_link])
        self.assertEqual(metadata_urls[0].get("type"), "FGDC")

        # a curated link is added in addition, it never replaces the imported one and
        # never gets nested into the already existing MetadataURL element
        self._curated_relation(dataset=self.other_dataset, layer=layer)

        capabilities = self._render_wms()

        metadata_urls = self.assertWmsMetadataUrls(
            capabilities, "node1.1.2", [imported_link, self.other_dataset.origin_url])
        self.assertEqual(metadata_urls[0].get("type"), "FGDC")
        self.assertEqual(metadata_urls[1].get("type"), METADATA_URL_TYPE)

    def test_metadata_url_without_online_resource_is_removed(self):
        """ A reference which lost its link is no valid xml and is not published. """
        self._store_document(
            WebMapService, WMS_PK, WMS_CAPABILITIES,
            document=self._document_with_metadata_url("node1.1.2"))

        capabilities = self._render_wms()

        self.assertWmsMetadataUrls(capabilities, "node1.1.2", [])

    def test_local_only_relation_is_not_published(self):
        """ A relation which is not intended for publication stays invisible. """
        layer = self._layer("node1.1.1")
        relation = MetadataRelation.objects.create(
            dataset_metadata=self.dataset, layer=layer, is_internal=True,
            origin=MetadataOriginEnum.CATALOGUE.value)

        self.assertEqual(
            relation.publication_kind, MetadataRelationPublicationEnum.LOCAL_ONLY)
        self.assertWmsMetadataUrls(self._render_wms(), "node1.1.1", [])

    def _dataset_without_origin_url(self):
        """ Return a copy of a fixture dataset record without a resolvable location. """
        dataset = DatasetMetadataRecord.objects.get(file_identifier=FIXTURE_DATASET)
        dataset.pk = None
        dataset.file_identifier = f"{FIXTURE_DATASET}.without.origin.url"
        dataset.code = f"{FIXTURE_DATASET}.without.origin.url"
        dataset.origin_url = None
        dataset.save()
        return dataset

    def test_relation_without_resolvable_link_is_not_published_but_reported(self):
        """ A coupling without a printable location is reported explicitly. """
        layer = self._layer("node1.1.1")
        relation = self._curated_relation(
            dataset=self._dataset_without_origin_url(), layer=layer)

        self.assertEqual(relation.publication_url, "")
        self.assertIn(
            "has no origin url to publish", "; ".join(relation.publication_blockers))

        with self.assertLogs(settings.ROOT_LOGGER, level="WARNING") as logged:
            capabilities = self._render_wms()

        self.assertWmsMetadataUrls(capabilities, "node1.1.1", [])
        self.assertIn(
            "has no origin url to publish", "; ".join(logged.output))

    def test_relation_without_dataset_has_no_xml_representation(self):
        """ A service metadata record of a layer can not be published as metadata url. """
        layer = self._layer("node1.1.1")
        service_record = ServiceMetadataRecord.objects.create(
            title="Service record of the fixture wms",
            code="service-record-of-fixture-wms",
            metadata_contact=self.dataset.metadata_contact)
        relation = self._curated_relation(layer=layer)
        relation.dataset_metadata = None
        relation.service_metadata = service_record
        relation.save()

        self.assertEqual(relation.publication_url, "")
        self.assertIn(
            "does not link a dataset metadata record",
            "; ".join(relation.publication_blockers))
        self.assertWmsMetadataUrls(self._render_wms(), "node1.1.1", [])

    def test_repeated_rendering_does_not_duplicate_published_links(self):
        """ Rendering the same state twice publishes the same document. """
        self._curated_relation(layer=self._layer("node1.1.1"))

        first = etree.tostring(
            self.assertWmsMetadataUrls(
                self._render_wms(), "node1.1.1", [self.dataset.origin_url])[0].getparent())

        second = etree.tostring(
            self.assertWmsMetadataUrls(
                self._render_wms(), "node1.1.1", [self.dataset.origin_url])[0].getparent())

        self.assertEqual(first, second)

    def test_removing_and_reassigning_a_relation_updates_the_published_links(self):
        """ The published document follows the coupling stored in the database. """
        layer = self._layer("node1.1.1")
        other_layer = self._layer("node1.1.2")
        relation = self._curated_relation(layer=layer)

        self.assertWmsMetadataUrls(
            self._render_wms(), "node1.1.1", [self.dataset.origin_url])

        relation.layer = other_layer
        relation.save()

        capabilities = self._render_wms()
        self.assertWmsMetadataUrls(capabilities, "node1.1.1", [])
        self.assertWmsMetadataUrls(
            capabilities, "node1.1.2", [self.dataset.origin_url])

        relation.delete()

        self.assertWmsMetadataUrls(self._render_wms(), "node1.1.2", [])

    def test_imported_evidence_relation_adds_no_link(self):
        """ The link of an imported relation is published through its remote metadata. """
        layer = self._layer("node1.1.1")
        MetadataRelation.objects.create(
            dataset_metadata=self.dataset, layer=layer, is_internal=False,
            origin=MetadataOriginEnum.CAPABILITIES.value)

        relation = MetadataRelation.objects.get(
            layer=layer, dataset_metadata=self.dataset)
        self.assertEqual(
            relation.publication_kind,
            MetadataRelationPublicationEnum.IMPORTED_EVIDENCE)
        self.assertWmsMetadataUrls(self._render_wms(), "node1.1.1", [])

    def test_curated_relation_is_published_for_feature_type(self):
        """ A curated relation publishes a reference on the feature type. """
        self._curated_relation(feature_type=self._feature_type("node2"))

        capabilities = self._render_wfs()

        self.assertEqual(
            [url.get(XLINK_HREF) for url in self._wfs_metadata_urls(
                capabilities, "node2")],
            [self.dataset.origin_url])
        # the wfs 2.0 schema defines a MetadataURL after the bounding box and before
        # the extended description of a feature type
        self.assertXpathCount(
            capabilities,
            "//wfs:FeatureType[wfs:Name='node2']/wfs:MetadataURL"
            "[preceding-sibling::wfs:ExtendedDescription]", 0)
        self.assertXpathCount(
            capabilities,
            "//wfs:FeatureType[wfs:Name='node2']/wfs:MetadataURL"
            "[preceding-sibling::ows:WGS84BoundingBox]", 1)

    def test_imported_link_of_a_feature_type_is_preserved(self):
        """ An imported link and a curated link are published side by side. """
        imported_link = "https://registry.example.com/id/de.example/imported-feature"
        feature_type = self._feature_type("node2")
        FeatureTypeRemoteMetadata.objects.create(
            describes=feature_type, link=imported_link)
        self._curated_relation(
            dataset=self.other_dataset, feature_type=feature_type)

        capabilities = self._render_wfs()

        self.assertEqual(
            [url.get(XLINK_HREF) for url in self._wfs_metadata_urls(
                capabilities, "node2")],
            [imported_link, self.other_dataset.origin_url])

    def test_reference_without_link_in_the_database_is_not_published(self):
        """ Only the references the database knows are published.

            The capabilities document of the fixture wfs holds a metadata reference for
            every feature type, but the fixtures have no remote metadata for them, so
            none of these references survives the rendering.
        """
        capabilities = self._render_wfs()

        self.assertXpathCount(
            capabilities, "//wfs:FeatureType[wfs:Name='node3']/wfs:MetadataURL", 0)


@tag("registry", "mappers")
class WmsMetadataUrlSerializerTest(TestCase):
    """ Tests the serializer which renders a metadata reference of a wms document.

        The wms 1.1.1 dtd defines a metadata reference as::

            <!ELEMENT MetadataURL (Format, OnlineResource)>
            <!ATTLIST MetadataURL type ( TC211 | FGDC ) #REQUIRED>
            <!ELEMENT Format (#PCDATA) >

        The documents of this protocol version are not namespaced, thats why this
        serializer is tested against such a document. The namespaced documents of the
        wms 1.3.0 are covered by :class:`PublishedMetadataLinksTest`.
    """

    LINK = "https://registry.example.com/id/de.example/dataset"

    @staticmethod
    def _layer():
        """ Return a layer of a wms 1.1.1 document without any metadata reference. """
        return etree.fromstring(
            '<Layer><Name>node</Name><Title>node</Title><Style/>'
            '<ScaleHint min="1" max="2"/><Layer/></Layer>')

    @staticmethod
    def _localnames(element):
        return [etree.QName(child).localname for child in element]

    def test_adds_the_required_information_to_a_bare_reference(self):
        """ A reference MrMap creates holds the format and the type it requires. """
        layer = self._layer()
        metadata_url = etree.SubElement(layer, "MetadataURL")
        online_resource = etree.SubElement(metadata_url, "OnlineResource")

        serialize_wms_metadata_url(
            None, online_resource, PublishedMetadataLink(link=self.LINK))

        self.assertEqual(metadata_url.get("type"), METADATA_URL_TYPE)
        self.assertEqual(online_resource.get(XLINK_HREF), self.LINK)
        self.assertEqual(self._localnames(metadata_url), ["Format", "OnlineResource"])
        self.assertEqual(metadata_url[0].text, METADATA_URL_FORMAT)
        # the reference was moved in front of all elements which must follow it
        self.assertEqual(
            self._localnames(layer),
            ["Name", "Title", "MetadataURL", "Style", "ScaleHint", "Layer"])

    def test_keeps_the_information_of_an_imported_reference(self):
        """ The type and format of a source document are never overwritten. """
        layer = self._layer()
        metadata_url = etree.SubElement(layer, "MetadataURL", {"type": "FGDC"})
        etree.SubElement(metadata_url, "Format").text = "application/octet-stream"
        online_resource = etree.SubElement(metadata_url, "OnlineResource")

        serialize_wms_metadata_url(
            None, online_resource, PublishedMetadataLink(link=self.LINK))

        self.assertEqual(metadata_url.get("type"), "FGDC")
        self.assertEqual(metadata_url[0].text, "application/octet-stream")
        self.assertEqual(self._localnames(metadata_url), ["Format", "OnlineResource"])

    def test_creates_a_reference_of_its_own(self):
        """ Each reference is a MetadataURL element of its own. """
        layer = self._layer()
        metadata_url = etree.SubElement(layer, "MetadataURL", {"type": "FGDC"})
        etree.SubElement(
            metadata_url, "Format").text = METADATA_URL_FORMAT
        etree.SubElement(metadata_url, "OnlineResource")
        # the generic element creation of the mappers reuses the MetadataURL element it
        # finds and only creates the OnlineResource of the new reference
        second_online_resource = etree.SubElement(metadata_url, "OnlineResource")

        serialize_wms_metadata_url(
            None, second_online_resource, PublishedMetadataLink(link=self.LINK))

        self.assertEqual(self._localnames(layer).count("MetadataURL"), 2)
        for metadata_url in layer.iterchildren("MetadataURL"):
            self.assertEqual(
                self._localnames(metadata_url), ["Format", "OnlineResource"])
