"""Profile rules are validated on save and answered as json:api errors (#1243).

The rule set is data on the profile (#1240); the write applies it (Q1 option
C on #1243). Pinned here, top-down:

* the migration content: the seeded generic profile carries the ISO 19139 v1
  rule set, every rule of it is assessable by the evaluator and holds over
  the corpus' complete fixture (`gdi-de-01.xml`) - rule data with a typo in
  an assertion would otherwise only surface as a wrong verdict;
* the evaluator: a rule that does not hold becomes a finding carrying rule
  id, family, severity and field; a rule whose XPath does not run is logged
  and answered citing the rule id - no engine text reaches the answer;
  nothing is evaluated whose shape the version can not assess (fail-closed,
  #1241);
* the endpoint: PATCH/PUT run the rules over the RESULTING document - the
  record's stored document with the row's and the payload's values written
  through the publish seam (#1244) - and refuse violations of `error`
  severity with one json:api error object per finding ({source.pointer,
  detail, rule, severity, meta.family, meta.severityCounts}); a refused
  write changes nothing, neither the row nor the document, and an accepted
  write commits exactly the document the rules were run over; warnings never
  refuse; a POST and records serving no document yet pass - nothing for the
  document rules to govern at validation time, their first document is the
  one this very save publishes at commit (#1244);
* the overlay converts the patched fields into the shape the write mapper
  reads (contact -> its four-field dict, keyword/language rows).
"""

from importlib import import_module
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings
from guardian.shortcuts import assign_perm
from lxml import etree
from registry.enums.metadata import MetadataOriginEnum
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.rules import (assessable_rule, evaluate_rules,
                                    findings_to_errors, overlay_write_values)
from registry.models.metadata import (GENERIC_ISO19139_PROFILE_PK,
                                      DatasetMetadataRecord, Keyword,
                                      Language, MetadataContact,
                                      MetadataProfile)
from rest_framework.test import APIClient
from tests.django.registry.tests_metadata_profile import ensure_generic_profile

ISO_DATA = (Path(__file__).resolve().parents[1]
            / "test_data" / "iso_metadata")

GENERIC_RULES = import_module(
    "registry.migrations.0052_the_generic_profile_names_its_rules"
).GENERIC_ISO19139_RULES

JSONAPI = "application/vnd.api+json"

#: one complete rule of the seeded set, as a shape reference for the guards
A_RULE = GENERIC_RULES[0]


def document_without(*local_names):
    """`dataset.xml` (complete, single MD_Metadata node) minus elements.

    This is the corpus' dataset-mapping fixture; `gdi-de-01.xml` would also
    hold every rule but maps as an application record.
    """
    root = etree.fromstring((ISO_DATA / "dataset.xml").read_bytes())
    for name in local_names:
        for element in root.xpath(f"//*[local-name()='{name}']"):
            element.getparent().remove(element)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def file_identifier_of(xml: bytes) -> str:
    return etree.fromstring(xml).xpath(
        "//*[local-name()='fileIdentifier']"
        "//*[local-name()='CharacterString']/text()")[0].strip()


def api(client, method, path, body=None):
    response = getattr(client, method)(
        path, body, format="vnd.api+json", HTTP_ACCEPT=JSONAPI)
    return response.status_code, (
        response.json() if response.content else {})


class RuleShapeTests(SimpleTestCase):
    """Only what the evaluator can assess may be evaluated (#1241 posture)."""

    def test_a_complete_rule_is_assessable(self):
        self.assertTrue(assessable_rule(A_RULE))

    def test_a_rule_without_an_assertion_is_not_assessable(self):
        self.assertFalse(assessable_rule({"type": "gdi-de-mandatory"}))

    def test_an_unknown_severity_is_not_assessable(self):
        self.assertFalse(assessable_rule({**A_RULE, "severity": "info"}))

    def test_a_field_the_overlay_cannot_place_is_not_assessable(self):
        # profile is relation bookkeeping, never a field of the mapped
        # document - the overlay skips it, so a rule pointing there can
        # never be assessed over the resulting document. (bounding_geometry
        # served as this example until #1246 gave it its reversible form -
        # it is assessable now)
        self.assertFalse(assessable_rule({**A_RULE, "field": "profile"}))

    def test_a_document_only_field_is_assessable(self):
        # the payload can not write date_stamp; the document carries it
        self.assertTrue(assessable_rule({**A_RULE, "field": "date_stamp"}))


class RuleEvaluationTests(SimpleTestCase):
    """What a rule set answers over a document."""

    def test_a_complete_document_holds_every_seeded_rule(self):
        complete = (ISO_DATA / "gdi-de-01.xml").read_bytes()
        self.assertEqual(evaluate_rules(GENERIC_RULES, complete), [])

    def test_a_rule_that_does_not_hold_becomes_a_finding(self):
        findings = evaluate_rules(GENERIC_RULES, document_without("title"))
        self.assertEqual([f.rule for f in findings], ["iso19139-title"])
        finding = findings[0]
        self.assertEqual(finding.family, "iso19139")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.field, "title")
        self.assertIn("title", str(finding.detail))

    def test_a_broken_assertion_is_answered_by_rule_id_not_engine_text(self):
        rule = {**A_RULE, "id": "iso19139-broken", "assert": "count(//["}
        with self.assertLogs("MrMap.root", level="ERROR") as logged:
            findings = evaluate_rules(
                [rule], (ISO_DATA / "gdi-de-01.xml").read_bytes())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "iso19139-broken")
        # the failure is graded error: a rule that could not run has no
        # verdict, and no verdict must not pass
        self.assertEqual(findings[0].severity, "error")
        detail = str(findings[0].detail)
        self.assertIn("iso19139-broken", detail)
        # GeoNetwork surfaced the raw XSLT complaint to the curator; here the
        # reason stays in the log entry and the answer only cites the rule
        self.assertNotIn("XPath", detail)
        self.assertTrue(any("iso19139-broken" in entry
                            for entry in logged.output))

    def test_findings_answer_as_grouped_jsonapi_error_objects(self):
        findings = evaluate_rules(
            GENERIC_RULES, document_without("title", "abstract", "dateStamp"))
        errors = findings_to_errors(findings)
        by_rule = {error["rule"]: error for error in errors}
        self.assertEqual(
            set(by_rule), {"iso19139-title", "iso19139-abstract",
                           "iso19139-date-stamp"})
        title = by_rule["iso19139-title"]
        self.assertEqual(title["source"]["pointer"], "/data/attributes/title")
        self.assertEqual(title["severity"], "error")
        self.assertEqual(title["status"], "400")
        self.assertEqual(title["meta"]["family"], "iso19139")
        # grouped severity counts of the whole run, per family (strings:
        # JSON:API error members are strings, see findings_to_errors)
        self.assertEqual(title["meta"]["severityCounts"],
                         {"iso19139": {"error": "2", "warning": "1"}})
        # errors lead, warnings ride along
        self.assertEqual([e["severity"] for e in errors],
                         ["error", "error", "warning"])
        self.assertEqual(
            by_rule["iso19139-date-stamp"]["source"]["pointer"],
            "/data/attributes/dateStamp")


class OverlayTests(SimpleTestCase):
    """The patched values reach the write mapper in the shape it reads."""

    def test_a_contact_becomes_the_dict_of_its_configured_fields(self):
        contact = MetadataContact(name="Stelle", person_name="Person",
                                  phone="123", email="a@b.c")
        values = {"metadata_contact": None}
        overlay_write_values(values, {"metadata_contact": contact})
        self.assertEqual(
            values["metadata_contact"],
            {"name": "Stelle", "person_name": "Person", "phone": "123",
             "email": "a@b.c"})

    def test_collection_rows_are_answered_like_the_reader(self):
        values = {"keywords": [], "languages": []}
        overlay_write_values(values, {
            "keywords": [Keyword(keyword="neu")],
            "languages": [Language(value=2)],
        })
        self.assertEqual(values["keywords"], [{"keyword": "neu"}])
        self.assertEqual(values["languages"], [{"value": 2}])

    def test_a_field_the_overlay_cannot_convert_keeps_its_extracted_row(self):
        # a name outside OVERLAYABLE_FIELDS - profile is relation
        # bookkeeping, not a field of the mapped document - keeps its row;
        # bounding_geometry converts since #1246 and can not serve here
        sentinel = object()
        values = {"profile": sentinel}
        overlay_write_values(values, {"profile": "a profile"})
        self.assertIs(values["profile"], sentinel)

    def test_the_write_mapper_reads_the_overlayed_values(self):
        # end to end at this level: extract, overlay a title, write - the
        # resulting document carries the new title and no other mapped
        # value moved
        xml = document_without("title")
        records = MDMetadataXmlMapper.extract_mapped_values(xml)
        records[0]["values"]["title"] = "Durch das Overlay geschrieben"
        out, _ = MDMetadataXmlMapper.write_mapped_records(xml, records)
        reread = MDMetadataXmlMapper.extract_mapped_values(out)
        self.assertEqual(reread[0]["values"]["title"],
                         "Durch das Overlay geschrieben")
        self.assertEqual(reread[0]["values"]["abstract"],
                         records[0]["values"]["abstract"])


class GenericProfileRuleContentTests(TestCase):
    """The seeded profile carries the v1 rule set as data (#1243)."""

    def test_the_seeded_generic_profile_names_the_iso_rule_set(self):
        profile = MetadataProfile.objects.get(pk=GENERIC_ISO19139_PROFILE_PK)
        self.assertEqual(profile.rules, GENERIC_RULES)
        self.assertTrue(all(assessable_rule(rule) for rule in profile.rules))
        self.assertEqual({rule["family"] for rule in profile.rules},
                         {"iso19139"})
        self.assertIn("iso19139-title",
                      [rule["id"] for rule in profile.rules])

    def test_gdi_de_and_inspire_join_as_later_rule_sets_of_their_own(self):
        # the v1 families are ISO only (decision 3 of the #1238 review); a
        # later rule set joins as data with its own family - the evaluator
        # accepts such data without a code branch, which is what the
        # acceptance criteria ask to be "registered, not coded"
        later = {**A_RULE, "id": "gdi-de-foo", "family": "gdi-de"}
        self.assertTrue(assessable_rule(later))


def api_body(pk=None, attributes=None, relationships=None,
             record_type="DatasetMetadataRecord"):
    data = {"type": record_type,
            "attributes": attributes or {},
            "relationships": relationships or {}}
    if pk:
        data["id"] = str(pk)
    return {"data": data}


@override_settings(MRMAP_METADATA_EDITOR_WRITES_ENABLED=True)
class ProfileRulesOnSaveApiTests(TestCase):
    """PATCH/PUT apply the profile rules over the resulting document."""

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(
            name="Validating contact")
        cls.profile = ensure_generic_profile()
        cls.doc = document_without("title", "abstract")
        cls.fid = file_identifier_of(cls.doc)
        cls.curator = get_user_model().objects.create_user(
            "rule-curator", password="test")

    def record(self, with_document=True, profile=None, document=None):
        record = DatasetMetadataRecord.objects.create(
            title="Record before the rules ran",
            file_identifier=self.fid,
            profile=profile or self.profile,
            metadata_contact=self.contact,
            dataset_contact=self.contact)
        if with_document:
            record.xml_backup_file.save(
                "record.xml", ContentFile(document or self.doc), save=False)
            record.save(mark_customized=False)
        assign_perm("registry.change_datasetmetadatarecord", self.curator)
        assign_perm("registry.change_datasetmetadatarecord", self.curator,
                    record)
        return record

    def api_client(self):
        client = APIClient()
        client.force_authenticate(user=self.curator)
        return client

    def patch(self, record, attributes):
        return api(self.api_client(), "patch",
                   f"/api/registry/dataset-metadata/{record.pk}",
                   api_body(pk=record.pk, attributes=attributes))

    def document_bytes(self, record):
        with open(record.xml_backup_file.path, "rb") as handle:
            return handle.read()

    def test_a_write_that_leaves_a_mandatory_element_missing_is_refused(self):
        record = self.record()
        before = self.document_bytes(record)
        status, answer = self.patch(record, {"title": "Curated title"})
        self.assertEqual(status, 400, answer)
        by_rule = {error["rule"]: error for error in answer["errors"]}
        # the patched title is evaluated over the RESULTING document, where
        # it holds; only the untouched abstract still violates a rule - the
        # verdict came from the resulting document, not the stored one
        self.assertEqual(set(by_rule), {"iso19139-abstract"})
        abstract = by_rule["iso19139-abstract"]
        self.assertEqual(abstract["severity"], "error")
        self.assertEqual(abstract["detail"],
                         next(r["message"] for r in GENERIC_RULES
                              if r["id"] == "iso19139-abstract"))
        self.assertEqual(abstract["source"]["pointer"],
                         "/data/attributes/abstract")
        self.assertEqual(abstract["meta"]["family"], "iso19139")
        # the counts describe the whole run over the resulting document:
        # the repaired title holds, only the abstract still violates, and
        # the document's own dateStamp is present -> no warning
        self.assertEqual(
            abstract["meta"]["severityCounts"],
            {"iso19139": {"error": "1", "warning": "0"}})
        # the refused write changed nothing: neither the row nor the document
        record.refresh_from_db()
        self.assertEqual(record.title, "Record before the rules ran")
        self.assertEqual(self.document_bytes(record), before)

    def test_a_write_that_repairs_the_resulting_document_is_accepted(self):
        record = self.record()
        before = self.document_bytes(record)
        status, answer = self.patch(
            record, {"title": "Curated title", "abstract": "Curated abstract"})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()
        self.assertEqual(record.title, "Curated title")
        # the accepted write IS the publish (#1244): the stored document
        # becomes the one the rules were run over - the drift this fixture
        # constructed (document without title and abstract while the row
        # carries both) is healed by the write, and nothing the document
        # held besides the patched fields is lost on the way
        document = self.document_bytes(record)
        self.assertNotEqual(document, before)
        values = MDMetadataXmlMapper \
            .extract_mapped_values(document)[0]["values"]
        self.assertEqual(values["title"], "Curated title")
        self.assertEqual(values["abstract"], "Curated abstract")
        self.assertEqual(str(values["file_identifier"]).strip(), self.fid)
        # repaired means whole: the served document answers a single record
        # and every seeded rule holds over it now
        root = etree.fromstring(document)
        self.assertEqual(len(root.xpath(
            "//*[local-name()='MD_Metadata']")), 1)
        self.assertEqual(evaluate_rules(GENERIC_RULES, document), [])

    def test_a_warning_never_refuses_a_write(self):
        warning_only = MetadataProfile.objects.create(
            name="warn-only", label="Warn only",
            rules=[dict(next(r for r in GENERIC_RULES
                             if r["id"] == "iso19139-date-stamp"))])
        document = document_without("dateStamp")
        record = self.record(profile=warning_only, document=document)
        status, answer = self.patch(record, {"title": "Still a good title"})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()
        self.assertEqual(record.title, "Still a good title")

    def test_a_record_its_document_does_not_carry_stays_fail_closed(self):
        # the validation needs THE node the record stands for; a record that
        # can not be located in its own document is refused instead of
        # answered as validated
        record = self.record()
        record.file_identifier = "not-the-documents-identifier"
        record.save(mark_customized=False)
        status, answer = self.patch(record, {"title": "Anywhere"})
        self.assertEqual(status, 400, answer)
        self.assertIn("rules", answer["errors"][0]["detail"])
        record.refresh_from_db()
        self.assertEqual(record.title, "Record before the rules ran")

    def test_a_post_with_a_rule_carrying_profile_still_creates_the_record(
            self):
        """A created record serves no document yet - the document rules have
        nothing to govern at validation time; the first document arrives with
        this save's publish (#1244, pinned in tests_metadata_record_publish).
        The shape guard still refused unassessable rule sets on the way (POST
        is not a free pass for data this version can not read)."""
        assign_perm("registry.add_datasetmetadatarecord", self.curator)
        body = api_body(
            attributes={"title": "Created under a rule set"},
            relationships={
                "metadataContact": {"data": {
                    "type": "MetadataContact",
                    "id": str(self.contact.pk)}},
                "datasetContact": {"data": {
                    "type": "MetadataContact",
                    "id": str(self.contact.pk)}}})
        status, answer = api(self.api_client(), "post",
                             "/api/registry/dataset-metadata", body)
        self.assertEqual(status, 201, answer)
        record = DatasetMetadataRecord.objects.get(pk=answer["data"]["id"])
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)

    def test_a_record_without_a_document_is_not_blocked_by_document_rules(
            self):
        """A legacy record serving no document: same posture as the POST at
        validation time - its first served document is the one this write
        publishes at commit (#1244)."""
        record = self.record(with_document=False)
        status, answer = self.patch(record, {"title": "No document, no rule"})
        self.assertEqual(status, 200, answer)
