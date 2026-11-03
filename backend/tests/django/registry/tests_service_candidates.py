""" Discovery and validation of the services which can deliver a record.

    Covers :mod:`registry.helper.metadata_resolution` and the two detail
    endpoints which answer it, see
    :class:`registry.views.metadata.MetadataResolutionViewSetMixin`.
"""

import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import resolve
from guardian.shortcuts import assign_perm
from requests import Session
from rest_framework.test import APIRequestFactory, force_authenticate

from registry.helper import metadata_resolution
from registry.helper.metadata_resolution import (CandidateSource,
                                                 CandidateState,
                                                 ServiceCandidate,
                                                 resolve_record,
                                                 validate_capabilities_candidate)
from registry.mappers.parsers.access_links import (ExtractionStatus, LinkType)
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataRelation, ServiceMetadataRecord)
from registry.models.service import CatalogueService
from tests.django.registry.tests_query_performance import QueryMeasurementMixin

TEST_DATA = Path(__file__).resolve().parents[1] / "test_data"
DATASET_XML = (TEST_DATA / "iso_metadata" / "dataset.xml").read_bytes()
SERVICE_XML = (TEST_DATA / "wms-service-metadata.xml").read_bytes()

DWD_WMS_CAPABILITIES = ("https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows"
                        "?service=wms&version=1.3.0&request=GetCapabilities")
DWD_WFS_CAPABILITIES = ("https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows"
                        "?service=wfs&version=2.0.0&request=GetCapabilities")
HH_CAPABILITIES = ("https://geodienste.hamburg.de/"
                   "DE_HH_WMS_INSPIRE_A1_7_Verkehrsnetze"
                   "?SERVICE=WMS&REQUEST=GetCapabilities")
RESOURCE_ID = ("https://registry.gdi-de.org/id/de.hh/"
               "72796D51-86BC-4343-AE77-85ECAFFACF15")
CODE_SPACE = "https://registry.gdi-de.org/id/de.hh/"
CODE = "72796D51-86BC-4343-AE77-85ECAFFACF15"


def iso_document(file_identifier):
    """ An iso record which advertises nothing but its file identifier. """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gmd:MD_Metadata'
        ' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier><gco:CharacterString>'
        f'{file_identifier}</gco:CharacterString></gmd:fileIdentifier>'
        '</gmd:MD_Metadata>').encode()


def iso_document_with_references(file_identifier, urls):
    """ An iso record which advertises the given metadata references.

        Every url carries the ``information`` function and no OGC hint, which
        is what the extraction classifies as a metadata reference.
    """
    links = "".join(
        "<gmd:onLine><gmd:CI_OnlineResource>"
        f"<gmd:linkage><gmd:URL>{url}</gmd:URL></gmd:linkage>"
        "<gmd:function><gmd:CI_OnLineFunctionCode"
        ' codeList="http://example.org/codelist"'
        ' codeListValue="information">information'
        "</gmd:CI_OnLineFunctionCode></gmd:function>"
        "</gmd:CI_OnlineResource></gmd:onLine>"
        for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gmd:MD_Metadata'
        ' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier><gco:CharacterString>'
        f'{file_identifier}</gco:CharacterString></gmd:fileIdentifier>'
        '<gmd:distributionInfo><gmd:MD_Distribution><gmd:transferOptions>'
        '<gmd:MD_DigitalTransferOptions>'
        f'{links}'
        '</gmd:MD_DigitalTransferOptions></gmd:transferOptions>'
        '</gmd:MD_Distribution></gmd:distributionInfo>'
        '</gmd:MD_Metadata>').encode()


def wms_capabilities(version="1.3.0", names=("RBSN_FF",)):
    layers = "".join(f"<Layer><Name>{name}</Name></Layer>" for name in names)
    return (
        f'<WMS_Capabilities version="{version}"'
        ' xmlns="http://www.opengis.net/wms">'
        f"<Service><Name>WMS</Name></Service>{layers}"
        "</WMS_Capabilities>").encode()


def wfs_capabilities(names=("ns:RBSN_FF",)):
    types = "".join(
        f"<FeatureType><Name>{name}</Name></FeatureType>" for name in names)
    return (
        '<WFS_Capabilities version="2.0.0"'
        ' xmlns="http://www.opengis.net/fes/2.0">'
        f"<ServiceIdentification><ServiceType>WFS</ServiceType>"
        "</ServiceIdentification>"
        f"<FeatureTypeList>{types}</FeatureTypeList>"
        "</WFS_Capabilities>").encode()


class _Answer:
    """ Stand-in for the streamed response which requests.Session.send gets.
    """

    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False

    def iter_content(self, chunk_size):
        yield self.content


def body_of(response):
    """ The json body of a response of a directly called view. """
    return json.loads(response.content) if response.content else {}


class ServiceCandidateDiscoveryTests(TestCase):
    """ What the resolver answers for a stored record, without any request. """

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name="Resolution contact")
        cls.dataset = cls.record(
            DatasetMetadataRecord, "de.dwd.geoserver.fach.RBSN_FF",
            DATASET_XML, code="rbsn-ff")

    @classmethod
    def record(cls, model, file_identifier, content, **attributes):
        if model is DatasetMetadataRecord:
            attributes.setdefault("dataset_contact", cls.contact)
        record = model.objects.create(
            metadata_contact=cls.contact, title=file_identifier,
            file_identifier=file_identifier, **attributes)
        record.xml_backup_file = SimpleUploadedFile("record.xml", content)
        record.save()
        return record

    def test_discovery_never_asks_an_endpoint(self):
        with mock.patch.object(Session, "send") as send:
            resolution = resolve_record(self.dataset, user=None)
        send.assert_not_called()
        self.assertEqual(resolution.status, ExtractionStatus.OK)
        self.assertEqual(
            resolution.file_identifier, "de.dwd.geoserver.fach.RBSN_FF")

    def test_the_own_document_answers_capabilities_candidates(self):
        resolution = resolve_record(self.dataset, user=None)
        by_url = {
            candidate.url: candidate for candidate in resolution.candidates}
        self.assertEqual(set(by_url), {DWD_WMS_CAPABILITIES,
                                       DWD_WFS_CAPABILITIES})
        wms = by_url[DWD_WMS_CAPABILITIES]
        self.assertEqual(
            (wms.kind, wms.service, wms.advertised_version, wms.derived,
             wms.source, wms.preferred),
            (LinkType.CAPABILITIES, "WMS", "1.3.0", False,
             CandidateSource.OWN_DISTRIBUTION, True))
        wfs = by_url[DWD_WFS_CAPABILITIES]
        # the record advertises a GetFeature call; the capabilities url of the
        # same endpoint is derived and the type name stays a hint
        self.assertEqual(
            (wfs.kind, wfs.service, wfs.advertised_version, wfs.derived,
             wfs.type_names),
            (LinkType.OGC_OPERATION, "WFS", "2.0.0", True, ("RBSN_FF",)))
        self.assertNotIn("typeNames", wfs.url)
        self.assertEqual(resolution.non_service_links, ())
        self.assertEqual(resolution.registered_targets, ())

    def test_a_service_record_naming_the_dataset_is_a_candidate(self):
        self.record(ServiceMetadataRecord, "A9A1A766-6C68-4B52-B30F"
                    "-90BA3190AF25", SERVICE_XML, code="hh-wms")
        named = self.record(DatasetMetadataRecord, "coupled-dataset",
                            iso_document("coupled-dataset"),
                            code_space=CODE_SPACE, code=CODE)
        resolution = resolve_record(named, user=None)
        coupled = [
            candidate for candidate in resolution.candidates
            if candidate.source == CandidateSource.COUPLED_SERVICE_RECORD]
        self.assertEqual([candidate.url for candidate in coupled],
                         [HH_CAPABILITIES])
        self.assertEqual(coupled[0].service, "WMS")
        self.assertTrue(any(RESOURCE_ID in evidence
                            for evidence in coupled[0].evidence))

    def test_the_lookup_of_coupled_service_records_is_bounded(self):
        for index in range(metadata_resolution.MAX_COUPLED_SERVICE_RECORDS + 1):
            self.record(ServiceMetadataRecord, f"hh-wms-{index}", SERVICE_XML,
                        code=f"hh-wms-{index}")
        named = self.record(DatasetMetadataRecord, "coupled-dataset",
                            iso_document("coupled-dataset"),
                            code_space=CODE_SPACE, code=CODE)
        resolution = resolve_record(named, user=None)
        self.assertTrue(resolution.truncated)
        self.assertEqual([candidate.url for candidate in resolution.candidates],
                         [HH_CAPABILITIES])

    def test_the_references_of_a_record_are_bounded(self):
        # A budget which cut something says so, and the record behind the
        # reference it cut is not asked.
        urls = [
            f"https://catalogue.example/record/{index}"
            for index in range(
                metadata_resolution.MAX_METADATA_REFERENCE_RECORDS + 1)]
        self.record(ServiceMetadataRecord, "cut-record", SERVICE_XML,
                    code="cut-record", origin_url=urls[-1])
        referencing = self.record(
            DatasetMetadataRecord, "referencing-dataset",
            iso_document_with_references("referencing-dataset", urls),
            code="referencing")
        resolution = resolve_record(referencing, user=None)
        self.assertTrue(resolution.truncated)
        self.assertEqual(resolution.candidates, ())

    def test_a_metadata_reference_names_the_record_it_reached(self):
        reference_url = "https://catalogue.example/record/hh-wms"
        referenced = self.record(ServiceMetadataRecord, "hh-wms", SERVICE_XML,
                                 code="hh-wms", origin_url=reference_url)
        referencing = self.record(
            DatasetMetadataRecord, "referencing-dataset",
            iso_document_with_references("referencing-dataset",
                                         [reference_url]),
            code="referencing")
        resolution = resolve_record(referencing, user=None)
        reached = [
            candidate for candidate in resolution.candidates
            if candidate.source
            == CandidateSource.METADATA_REFERENCE_RECORD]
        self.assertEqual([candidate.url for candidate in reached],
                         [HH_CAPABILITIES])
        self.assertTrue(any(str(referenced.origin_url) in evidence
                            for evidence in reached[0].evidence))

    def test_registered_resources_answer_apart_from_the_candidates(self):
        service = self.record(ServiceMetadataRecord, "lfu-wms", SERVICE_XML,
                              code="lfu-wms")
        catalogue = CatalogueService.objects.create(
            version=202, metadata_contact=self.contact,
            service_contact=self.contact)
        MetadataRelation.objects.create(
            service_metadata=service, csw=catalogue, origin=5)
        resolution = resolve_record(service, user=None)
        self.assertEqual(
            [(target.resource_type, target.id)
             for target in resolution.registered_targets],
            [("csw", catalogue.pk)])
        self.assertTrue(resolution.candidates)

    def test_a_record_without_a_document_answers_its_state(self):
        empty = DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact, dataset_contact=self.contact,
            title="No document", code="no-document")
        resolution = resolve_record(empty, user=None)
        self.assertEqual(resolution.status, ExtractionStatus.MISSING)
        self.assertEqual(resolution.candidates, ())
        broken = self.record(DatasetMetadataRecord, "broken", b"<unbalanced",
                             code="broken")
        self.assertEqual(
            resolve_record(broken, user=None).status,
            ExtractionStatus.MALFORMED)

    def test_the_validation_of_a_url_the_record_never_advertised_is_refused(
            self):
        resolution = resolve_record(self.dataset, user=None)
        candidate = resolution.candidates[0]
        with mock.patch.object(Session, "send") as send:
            result = validate_capabilities_candidate(
                candidate, "https://example.org/other?REQUEST=GetCapabilities")
        send.assert_not_called()
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNAVAILABLE, "not-advertised"))


class CapabilitiesValidationTests(SimpleTestCase):
    """ What one bounded capabilities request answers. """

    def candidate(self, url=DWD_WMS_CAPABILITIES, **attributes):
        attributes.setdefault("original_url", url)
        return ServiceCandidate(
            url=url, kind=LinkType.CAPABILITIES,
            source=CandidateSource.OWN_DISTRIBUTION, **attributes)

    def validate(self, candidate=None, url=None, content=b"",
                 status_code=200):
        with mock.patch.object(
                Session, "send",
                return_value=_Answer(content, status_code)) as send:
            result = validate_capabilities_candidate(
                candidate or self.candidate(), url or DWD_WMS_CAPABILITIES)
        return result, send

    def test_confirmed_hints_resolve_the_candidate(self):
        result, _ = self.validate(
            self.candidate(type_names=("RBSN_FF",)),
            content=wfs_capabilities(names=("ns:RBSN_FF",)))
        self.assertEqual(
            (result.state, result.detail, result.service_type,
             result.service_version),
            (CandidateState.RESOLVED, "ok", "WFS", "2.0.0"))
        # a hint of the record which the capabilities name behind a namespace
        # prefix is confirmed, not guessed
        self.assertEqual(result.matched_names, ("ns:RBSN_FF",))
        self.assertEqual(result.unresolved_hints, ())

    def test_an_unconfirmed_hint_needs_a_user_decision(self):
        result, _ = self.validate(
            self.candidate(layers=("own-layer",)),
            content=wms_capabilities(names=("another-layer",)))
        self.assertEqual(
            (result.state, result.detail, result.unresolved_hints),
            (CandidateState.AMBIGUOUS, "unresolved-hints", ("own-layer",)))

    def test_the_answered_names_are_bounded(self):
        with mock.patch.object(metadata_resolution, "ADVERTISED_NAMES_LIMIT", 2):
            result, _ = self.validate(
                content=wms_capabilities(names=("a", "b", "c")))
        self.assertEqual(result.advertised_names, ("a", "b"))
        self.assertTrue(result.names_truncated)

    def test_the_request_is_anonymous_and_bounded(self):
        _, send = self.validate(content=wms_capabilities())
        kwargs = send.call_args.kwargs
        prepared = send.call_args.args[0]
        self.assertEqual(
            (kwargs["timeout"], kwargs["stream"], kwargs["allow_redirects"]),
            ((3, 3), True, False))
        self.assertEqual(prepared.method, "GET")
        # nothing of the incoming request is forwarded upstream
        self.assertNotIn("Cookie", prepared.headers)
        self.assertNotIn("Authorization", prepared.headers)

    def test_a_redirect_is_not_followed(self):
        result, _ = self.validate(status_code=302)
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNAVAILABLE, "redirected"))

    def test_a_protected_or_failing_endpoint_is_unavailable(self):
        for status_code, detail in ((401, "denied"), (403, "denied"),
                                    (500, "upstream")):
            with self.subTest(status_code=status_code):
                result, _ = self.validate(status_code=status_code)
                self.assertEqual(
                    (result.state, result.detail),
                    (CandidateState.UNAVAILABLE, detail))

    def test_an_ogc_exception_report_answers_its_code(self):
        result, _ = self.validate(content=(
            b"<ServiceExceptionReport version='1.3.0'>"
            b"<ServiceException exceptionCode='OperationNotSupported'>"
            b"nope</ServiceException></ServiceExceptionReport>"))
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNAVAILABLE,
             "exception-report:OperationNotSupported"))

    def test_content_which_is_not_capabilities_is_answered(self):
        for content, state, detail in (
                (b"<html", CandidateState.UNAVAILABLE, "parse"),
                (b"<MD_Metadata/>", CandidateState.UNSUPPORTED,
                 "unsupported-service"),
                (wms_capabilities(version="1.1.0"),
                 CandidateState.UNSUPPORTED, "unsupported-version"),
                (b"<WMS_Capabilities/>", CandidateState.UNAVAILABLE,
                 "no-version")):
            with self.subTest(content=content):
                result, _ = self.validate(content=content)
                self.assertEqual((result.state, result.detail),
                                 (state, detail))

    def test_the_response_size_and_time_are_bounded(self):
        with mock.patch.object(
                metadata_resolution, "CAPABILITIES_RESPONSE_LIMIT", 10):
            result, _ = self.validate(content=b"x" * 11)
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNAVAILABLE, "limit"))

        with mock.patch.object(metadata_resolution, "time") as watched:
            watched.monotonic.side_effect = [0, 1000]
            result, _ = self.validate(content=wms_capabilities())
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNAVAILABLE, "limit"))

    def test_a_url_of_another_scheme_is_never_fetched(self):
        candidate = self.candidate(url="file:///etc/passwd",
                                   original_url="file:///etc/passwd")
        with mock.patch.object(Session, "send") as send:
            result = validate_capabilities_candidate(
                candidate, "file:///etc/passwd")
        send.assert_not_called()
        self.assertEqual(
            (result.state, result.detail),
            (CandidateState.UNSUPPORTED, "not-fetchable"))


class ServiceCandidateEndpointTests(QueryMeasurementMixin, TestCase):
    """ The two detail endpoints of a metadata record. """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.contact = MetadataContact.objects.create(name="Endpoint contact")
        cls.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact, dataset_contact=cls.contact,
            title="RBSN_FF",
            file_identifier="de.dwd.geoserver.fach.RBSN_FF", code="rbsn-ff")
        cls.dataset.xml_backup_file = SimpleUploadedFile(
            "dataset.xml", DATASET_XML)
        cls.dataset.save()

    def path(self, action=None):
        base = f"/api/registry/dataset-metadata/{self.dataset.pk}"
        return f"{base}/{action}" if action else base

    JSONAPI = "application/vnd.api+json"

    def call(self, path, user, accept=None, **params):
        """ Ask a metadata endpoint directly, like the neighbor tests do.

            The resolution actions render plain JSON, so they are asked with
            ``application/json`` - exactly like the live preview endpoints,
            which they mirror; the JSON:API endpoints are asked with the
            JSON:API media type.
        """
        request = APIRequestFactory().get(
            path, params,
            HTTP_ACCEPT=accept or self.JSONAPI)
        if user is not None:
            force_authenticate(request, user=user)
        callback, _, kwargs = resolve(path)
        response = callback(request, **kwargs)
        if getattr(response, "is_rendered", True) is False:
            response.render()
        return response

    def ask(self, path, user, **params):
        return self.call(path, user, accept="application/json", **params)

    def test_discovery_answers_the_candidates_of_the_record(self):
        admin = get_user_model().objects.create_superuser(
            "candidate-admin", password="test")
        response = self.ask(self.path("service-candidates"), admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = body_of(response)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(
            {candidate["url"] for candidate in body["candidates"]},
            {DWD_WMS_CAPABILITIES, DWD_WFS_CAPABILITIES})
        preferred = [candidate for candidate in body["candidates"]
                     if candidate["preferred"]]
        self.assertEqual([candidate["url"] for candidate in preferred],
                         [DWD_WMS_CAPABILITIES])
        self.assertEqual(
            preferred[0]["state"], "unvalidated")

    def test_the_actions_answer_for_the_same_users_as_retrieve_does(self):
        reader = get_user_model().objects.create_user(
            "candidate-reader", password="test")
        assign_perm("registry.view_datasetmetadatarecord", reader,
                    self.dataset)
        for user in (self.user, reader, None):
            for action in (None, "service-candidates"):
                with self.subTest(user=user, action=action):
                    target = self.ask if action else self.call
                    self.assertEqual(
                        target(self.path(action), user).status_code,
                        self.call(self.path(), user).status_code)
        # the reader may see the record, so the discovery answers for them
        self.assertEqual(
            self.ask(self.path("service-candidates"), reader).status_code,
            200)

    def test_a_url_of_another_record_is_refused_for_the_owner_too(self):
        admin = get_user_model().objects.create_superuser(
            "scoped-admin", password="test")
        other = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact, title="HH WMS", code="hh-wms")
        other.xml_backup_file = SimpleUploadedFile("service.xml", SERVICE_XML)
        other.save()
        with mock.patch.object(
                metadata_resolution._BoundedCapabilitiesSession,
                "send") as asked:
            response = self.ask(
                self.path("validate-service-candidate"), admin,
                url=HH_CAPABILITIES)
        asked.assert_not_called()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body_of(response), {"error": "not-advertised"})

    def test_validation_asks_only_an_endpoint_the_record_advertised(self):
        admin = get_user_model().objects.create_superuser(
            "validate-admin", password="test")
        path = self.path("validate-service-candidate")
        with mock.patch.object(
                metadata_resolution._BoundedCapabilitiesSession,
                "send", return_value=wms_capabilities()) as asked:
            response = self.ask(path, admin, url=DWD_WMS_CAPABILITIES)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(asked.call_count, 1)
        body = body_of(response)
        self.assertEqual(
            (body["url"], body["state"], body["service_type"]),
            (DWD_WMS_CAPABILITIES, "resolved", "WMS"))

        with mock.patch.object(
                metadata_resolution._BoundedCapabilitiesSession,
                "send") as asked:
            refused = self.ask(path, admin,
                               url="https://example.org/secret")
        asked.assert_not_called()
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(body_of(refused), {"error": "not-advertised"})

    def test_validation_requires_a_url(self):
        admin = get_user_model().objects.create_superuser(
            "url-admin", password="test")
        response = self.ask(self.path("validate-service-candidate"), admin)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body_of(response), {"error": "url-required"})
