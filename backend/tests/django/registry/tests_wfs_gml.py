"""Tests covering the WFS 2.0 GML 3.2 GetFeature conversion (issue #668)."""
from unittest import mock

from django.test import SimpleTestCase

from lxml import etree

from registry.helper.preview import PreviewError, gml_features, is_gml32, parse_xml, validate_features
from registry.ows_lib.wfs import gml


WFS_NS = 'xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:ms="http://ns.example.com/ms"'
GML_NS = 'xmlns:gml="http://www.opengis.net/gml/3.2"'
XLINK_NS = 'xmlns:xlink="http://www.w3.org/1999/xlink"'
CRS = "urn:ogc:def:crs:EPSG::4326"


def collection(*members, srs_name=""):
    """Wrap feature members into a GetFeature response root."""
    return (f'<wfs:FeatureCollection {WFS_NS} {GML_NS} {XLINK_NS} {srs_name}>'
            f'{"".join(members)}</wfs:FeatureCollection>')


def member(geometry, identifier='gml:id="ms.1"', properties="", srs_name=""):
    """One wfs:member holding a qualified feature with a geometry and simple properties."""
    return (f'<wfs:member><ms:Feature {identifier} {srs_name}>'
            f'<ms:geom>{geometry}</ms:geom>{properties}</ms:Feature></wfs:member>')


def convert(document, stored_geometry_property="ms:geom", limit=250, requested_crs="EPSG:4326"):
    """Convert a document exactly like the preview does: parse it, then take the shape."""
    return gml.feature_collection(etree.fromstring(document.encode("utf-8")), limit,
                                  stored_geometry_property, requested_crs)


class GmlGeometryTests(SimpleTestCase):
    """The geometry subset of the supported GML encodings and the refusals around it."""

    def assert_geometry(self, geometry, document):
        converted = convert(collection(member(document)))
        validate_features(converted)
        self.assertEqual(converted["features"][0]["geometry"], geometry)

    def test_point_is_converted_with_the_axis_order_of_its_crs(self):
        """A latitude first gml:pos becomes longitude first, as the GeoJSON contract states."""
        self.assert_geometry({"type": "Point", "coordinates": [13.2, 52.1]},
                             f'<gml:Point srsName="{CRS}"><gml:pos>52.1 13.2</gml:pos></gml:Point>')

    def test_line_string_is_converted_position_by_position(self):
        self.assert_geometry(
            {"type": "LineString", "coordinates": [[13.1, 52.1], [13.2, 52.2]]},
            '<gml:LineString><gml:posList>52.1 13.1 52.2 13.2</gml:posList></gml:LineString>')

    def test_polygon_with_a_hole_keeps_its_rings(self):
        exterior = "52.0 13.0 52.0 14.0 53.0 14.0 53.0 13.0 52.0 13.0"
        interior = "52.4 13.4 52.4 13.6 52.6 13.6 52.4 13.4"
        self.assert_geometry(
            {"type": "Polygon", "coordinates": [
                [[13.0, 52.0], [14.0, 52.0], [14.0, 53.0], [13.0, 53.0], [13.0, 52.0]],
                [[13.4, 52.4], [13.6, 52.4], [13.6, 52.6], [13.4, 52.4]]]},
            f'<gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{exterior}'
            f'</gml:posList></gml:LinearRing></gml:exterior>'
            f'<gml:interior><gml:LinearRing><gml:posList>{interior}'
            f'</gml:posList></gml:LinearRing></gml:interior></gml:Polygon>')

    def test_a_ring_without_the_repeated_position_is_closed(self):
        exterior = "52.0 13.0 52.0 14.0 53.0 14.0 53.0 13.0"
        self.assert_geometry(
            {"type": "Polygon", "coordinates": [
                [[13.0, 52.0], [14.0, 52.0], [14.0, 53.0], [13.0, 53.0], [13.0, 52.0]]]},
            f'<gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{exterior}'
            f'</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>')

    def test_surface_is_converted_from_its_polygon_patch(self):
        ring = "52.0 13.0 52.0 14.0 53.0 14.0 53.0 13.0 52.0 13.0"
        self.assert_geometry(
            {"type": "Polygon", "coordinates": [
                [[13.0, 52.0], [14.0, 52.0], [14.0, 53.0], [13.0, 53.0], [13.0, 52.0]]]},
            f'<gml:Surface><gml:patches><gml:PolygonPatch><gml:exterior>'
            f'<gml:LinearRing><gml:posList>{ring}</gml:posList></gml:LinearRing>'
            f'</gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface>')

    def test_multipoint_and_multilinestring_are_converted(self):
        self.assert_geometry(
            {"type": "MultiPoint", "coordinates": [[13.1, 52.1], [13.2, 52.2]]},
            '<gml:MultiPoint><gml:pointMember><gml:Point><gml:pos>52.1 13.1</gml:pos>'
            '</gml:Point></gml:pointMember><gml:pointMember><gml:Point>'
            '<gml:pos>52.2 13.2</gml:pos></gml:Point></gml:pointMember></gml:MultiPoint>')
        self.assert_geometry(
            {"type": "MultiLineString", "coordinates": [[[13.1, 52.1], [13.2, 52.2]]]},
            '<gml:MultiLineString><gml:lineStringMember><gml:LineString>'
            '<gml:posList>52.1 13.1 52.2 13.2</gml:posList></gml:LineString>'
            '</gml:lineStringMember></gml:MultiLineString>')

    def test_multicurve_of_linestrings_becomes_a_multilinestring(self):
        self.assert_geometry(
            {"type": "MultiLineString", "coordinates": [[[13.1, 52.1], [13.2, 52.2]]]},
            '<gml:MultiCurve><gml:curveMember><gml:LineString>'
            '<gml:posList>52.1 13.1 52.2 13.2</gml:posList></gml:LineString>'
            '</gml:curveMember></gml:MultiCurve>')

    def test_multisurface_and_multipolygon_become_a_multipolygon(self):
        ring = "52.0 13.0 52.0 14.0 53.0 14.0 53.0 13.0 52.0 13.0"
        polygon = (f'<gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{ring}'
                   f'</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>')
        surface = (f'<gml:Surface><gml:patches><gml:PolygonPatch><gml:exterior>'
                   f'<gml:LinearRing><gml:posList>{ring}</gml:posList></gml:LinearRing>'
                   f'</gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface>')
        expected = {"type": "MultiPolygon", "coordinates": [[
            [[13.0, 52.0], [14.0, 52.0], [14.0, 53.0], [13.0, 53.0], [13.0, 52.0]]]]}
        self.assert_geometry(expected,
                             f'<gml:MultiPolygon><gml:polygonMember>{polygon}'
                             f'</gml:polygonMember></gml:MultiPolygon>')
        self.assert_geometry(expected,
                             f'<gml:MultiSurface><gml:surfaceMember>{surface}'
                             f'</gml:surfaceMember></gml:MultiSurface>')

    def test_multigeometry_keeps_the_types_of_its_members(self):
        converted = convert(collection(member(
            '<gml:MultiGeometry><gml:geometryMember><gml:Point>'
            '<gml:pos>52.1 13.1</gml:pos></gml:Point></gml:geometryMember>'
            '<gml:geometryMember><gml:LineString>'
            '<gml:posList>52.1 13.1 52.2 13.2</gml:posList></gml:LineString>'
            '</gml:geometryMember></gml:MultiGeometry>')))
        validate_features(converted)
        self.assertEqual(converted["features"][0]["geometry"], {
            "type": "GeometryCollection", "geometries": [
                {"type": "Point", "coordinates": [13.1, 52.1]},
                {"type": "LineString", "coordinates": [[13.1, 52.1], [13.2, 52.2]]}]})

    def test_an_empty_aggregate_is_refused(self):
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member("<gml:MultiPoint></gml:MultiPoint>")))
        self.assertEqual(raised.exception.code, "gmlSchema")

    def test_an_aggregate_of_the_wrong_member_type_is_refused(self):
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member(
                '<gml:MultiPoint><gml:pointMember><gml:LineString>'
                '<gml:posList>52.1 13.1 52.2 13.2</gml:posList></gml:LineString>'
                '</gml:pointMember></gml:MultiPoint>')))
        self.assertEqual(raised.exception.code, "gmlSchema")


class GmlCrsTests(SimpleTestCase):
    """Every form of the requested geographic CRS, in both axis orders."""

    def assert_coordinates(self, document, coordinates):
        converted = convert(document)
        validate_features(converted)
        self.assertEqual(converted["features"][0]["geometry"]["coordinates"], coordinates)

    def point(self, srs_name, first, second):
        return f'<gml:Point srsName="{srs_name}"><gml:pos>{first} {second}</gml:pos></gml:Point>'

    def test_every_form_of_the_latitude_first_crs_is_accepted(self):
        for srs_name in ("EPSG:4326", CRS, "http://www.opengis.net/def/crs/EPSG/0/4326"):
            with self.subTest(srs_name=srs_name):
                self.assert_coordinates(
                    collection(member(self.point(srs_name, "52.1", "13.2"))), [13.2, 52.1])

    def test_every_form_of_the_longitude_first_crs_is_accepted(self):
        for srs_name in ("CRS:84", "urn:ogc:def:crs:OGC::CRS84", "urn:ogc:def:crs:OGC:1.3:CRS84",
                         "http://www.opengis.net/def/crs/OGC/1.3/CRS84"):
            with self.subTest(srs_name=srs_name):
                self.assert_coordinates(
                    collection(member(self.point(srs_name, "13.2", "52.1"))), [13.2, 52.1])

    def test_the_geometry_srsname_wins_over_the_feature_and_the_response(self):
        self.assert_coordinates(collection(
            member(self.point("CRS:84", "13.2", "52.1"), srs_name=f'srsName="{CRS}"'),
            srs_name='srsName="urn:ogc:def:crs:EPSG::4979"'), [13.2, 52.1])

    def test_a_projected_or_foreign_crs_is_refused_instead_of_reprojected(self):
        for srs_name in ("urn:ogc:def:crs:EPSG::25832", "urn:ogc:def:crs:EPSG::4979", "EPSG:3857",
                         "urn:ogc:def:crs:OGC::CRS84h"):
            with self.subTest(srs_name=srs_name):
                with self.assertRaises(gml.GmlError) as raised:
                    convert(collection(member(self.point(srs_name, "52.1", "13.2"))))
                self.assertEqual(raised.exception.code, "crs")

    def test_a_missing_srsname_falls_back_to_the_requested_crs(self):
        self.assert_coordinates(collection(
            member("<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>")), [13.2, 52.1])
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member("<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>")),
                    requested_crs="urn:ogc:def:crs:EPSG::25832")
        self.assertEqual(raised.exception.code, "crs")


class GmlDimensionTests(SimpleTestCase):
    """Heights are refused, never dropped in silence."""

    def test_a_stated_two_dimensional_crs_is_accepted(self):
        self.assertEqual(convert(collection(member(
            '<gml:Point srsDimension="2"><gml:pos>52.1 13.2</gml:pos></gml:Point>')))
            ["features"][0]["geometry"]["coordinates"], [13.2, 52.1])

    def test_a_three_dimensional_position_is_refused(self):
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member(
                '<gml:Point srsDimension="3"><gml:pos>52.1 13.2 100</gml:pos></gml:Point>')))
        self.assertEqual(raised.exception.code, "gmlDimension")

    def test_a_position_with_too_many_values_without_a_dimension_is_refused(self):
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member(
                "<gml:Point><gml:pos>52.1 13.2 100</gml:pos></gml:Point>")))
        self.assertEqual(raised.exception.code, "gmlDimension")

    def test_a_pos_list_that_is_not_a_pair_sequence_is_refused(self):
        with self.assertRaises(gml.GmlError) as raised:
            convert(collection(member(
                '<gml:LineString><gml:posList>52.1 13.1 52.2</gml:posList></gml:LineString>')))
        self.assertEqual(raised.exception.code, "malformed")


class GmlRefusalTests(SimpleTestCase):
    """Everything outside the subset is refused with its own state."""

    def assert_refused(self, document, code, status=422, **kwargs):
        with self.assertRaises(gml.GmlError) as raised:
            convert(document, **kwargs)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(raised.exception.status, status)

    def test_deprecated_coordinates_and_coord_encoding_is_refused(self):
        self.assert_refused(collection(member(
            '<gml:Point><gml:coordinates>13.2,52.1</gml:coordinates></gml:Point>')), "gmlSchema")
        self.assert_refused(collection(member(
            '<gml:Point><gml:coord><gml:X>13.2</gml:X><gml:Y>52.1</gml:Y>'
            '</gml:coord></gml:Point>')), "gmlSchema")

    def test_remote_references_are_never_read(self):
        self.assert_refused(collection(
            '<wfs:member><ms:Feature gml:id="ms.1">'
            '<ms:geom xlink:href="http://example.com/other#geom"/></ms:Feature></wfs:member>'),
            "gmlRemote")

    def test_a_geometry_of_another_namespace_is_refused(self):
        self.assert_refused(collection(
            '<wfs:member><ms:Feature gml:id="ms.1">'
            '<ms:geom><other:Point xmlns:other="http://example.com/other">'
            '<gml:pos>52.1 13.2</gml:pos></other:Point></ms:geom>'
            '</ms:Feature></wfs:member>'), "gmlSchema")

    def test_unsupported_geometries_are_refused(self):
        for geometry in ("<gml:Solid/>", "<gml:CompositeSurface/>",
                         '<gml:Surface><gml:patches><gml:Triangle><gml:exterior>'
                         '<gml:LinearRing><gml:posList>52.0 13.0 52.0 14.0 53.0 13.0 52.0 13.0'
                         '</gml:posList></gml:LinearRing></gml:exterior></gml:Triangle>'
                         '</gml:patches></gml:Surface>'):
            with self.subTest(geometry=geometry):
                self.assert_refused(collection(member(geometry)), "gmlSchema")

    def test_a_non_numeric_position_is_refused(self):
        self.assert_refused(collection(member(
            "<gml:Point><gml:pos>NaN 13.2</gml:pos></gml:Point>")), "malformed")

    def test_an_empty_answer_is_an_empty_collection(self):
        converted = convert(f'<wfs:FeatureCollection {WFS_NS} {GML_NS}></wfs:FeatureCollection>')
        validate_features(converted)
        self.assertEqual(converted["features"], [])

    def test_a_document_that_is_not_a_feature_collection_is_refused(self):
        self.assert_refused(f'<wfs:ExceptionReport {WFS_NS}></wfs:ExceptionReport>', "format")
        self.assert_refused(collection("<wfs:notAMember/>"), "format")

    def test_more_members_than_the_limit_refuses_the_response_as_upstream(self):
        members = [member(f"<gml:Point><gml:pos>52.{count} 13.{count}</gml:pos></gml:Point>",
                          identifier=f'gml:id="ms.{count}"') for count in range(3)]
        self.assert_refused(collection(*members), "limit", status=502, limit=2)

    def test_complex_property_content_is_refused(self):
        self.assert_refused(collection(member(
            "<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>",
            properties="<ms:nested><ms:child>x</ms:child></ms:nested>")), "gmlSchema")

    def test_a_feature_with_two_geometry_properties_needs_the_stored_schema(self):
        self.assert_refused(collection(member(
            "<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>",
            properties="<ms:other><gml:Point><gml:pos>52.2 13.3</gml:pos>"
                       "</gml:Point></ms:other>")), "gmlSchema", stored_geometry_property=None)

    def test_a_member_without_exactly_one_feature_is_refused(self):
        self.assert_refused(collection("<wfs:member/>"), "gmlSchema")


class GmlFeatureTests(SimpleTestCase):
    """The feature part of the contract: identifiers, properties and null geometries."""

    def test_features_keep_their_identifier_and_simple_properties(self):
        converted = convert(collection(
            member("<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>", identifier='fid="ms.7"',
                   properties="<ms:name>Rathaus</ms:name><ms:height>36</ms:height>"),
            member("<gml:Point><gml:pos>52.2 13.3</gml:pos></gml:Point>")))
        validate_features(converted)
        self.assertEqual(converted["type"], "FeatureCollection")
        self.assertEqual([feature.get("id") for feature in converted["features"]], ["ms.7", "ms.1"])
        self.assertEqual(converted["features"][0]["properties"], {"name": "Rathaus", "height": "36"})
        self.assertEqual(converted["features"][1]["properties"], {})

    def test_a_null_geometry_is_a_feature_without_geometry(self):
        converted = convert(collection(
            '<wfs:member><ms:Feature gml:id="ms.1">'
            '<ms:geom gml:nil="true"></ms:geom><ms:name>Rathaus</ms:name>'
            '</ms:Feature></wfs:member>'))
        validate_features(converted)
        self.assertIsNone(converted["features"][0]["geometry"])
        self.assertEqual(converted["features"][0]["properties"], {"name": "Rathaus"})

    def test_the_stored_schema_names_which_property_holds_the_geometry(self):
        converted = convert(collection(
            '<wfs:member><ms:Feature gml:id="ms.1"><ms:status>ok</ms:status>'
            '<ms:location><gml:Point><gml:pos>52.2 13.3</gml:pos></gml:Point></ms:location>'
            '<ms:geom><gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point></ms:geom>'
            '</ms:Feature></wfs:member>'), stored_geometry_property="ms:geom")
        validate_features(converted)
        self.assertEqual(converted["features"][0]["geometry"]["coordinates"], [13.2, 52.1])
        self.assertEqual(converted["features"][0]["properties"], {"status": "ok"})

    def test_a_bounded_by_is_not_treated_as_a_feature(self):
        converted = convert(collection(
            '<wfs:boundedBy><gml:Envelope srsName="%s">'
            '<gml:lowerCorner>52.0 13.0</gml:lowerCorner>'
            '<gml:upperCorner>53.0 14.0</gml:upperCorner></gml:Envelope></wfs:boundedBy>' % CRS,
            member("<gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point>")))
        self.assertEqual(len(converted["features"]), 1)


class GmlPreviewTests(SimpleTestCase):
    """How the conversion joins the preview: negotiation, states and the safe parse."""

    def stored_property(self, name):
        """Patch away the stored schema lookup only, which is a database query."""
        patcher = mock.patch("registry.helper.preview.FeatureTypeProperty")
        stored = patcher.start()
        self.addCleanup(patcher.stop)
        stored.objects.filter.return_value.values_list.return_value.first.return_value = name

    def test_only_a_gml_3_2_token_is_negotiated_as_gml(self):
        for token in ("application/gml+xml; version=3.2", "GML32", "application/gml+xml;version=3.2"):
            with self.subTest(token=token):
                self.assertTrue(is_gml32(token))
        for token in ("application/gml+xml; version=3.1", "application/gml+xml", "application/json",
                      "gml", "text/xml"):
            with self.subTest(token=token):
                self.assertFalse(is_gml32(token))

    def test_the_stored_schema_selects_the_geometry_property(self):
        root = parse_xml(collection(
            '<wfs:member><ms:Feature gml:id="ms.1">'
            '<ms:location><gml:Point><gml:pos>52.2 13.3</gml:pos></gml:Point></ms:location>'
            '<ms:geom><gml:Point><gml:pos>52.1 13.2</gml:pos></gml:Point></ms:geom>'
            '</ms:Feature></wfs:member>'))
        self.stored_property("ms:location")
        features = gml_features(root, None)
        validate_features(features)
        self.assertEqual(features["features"][0]["geometry"]["coordinates"], [13.3, 52.2])
        # The remaining geometric property is not an attribute the renderer could carry.
        self.assertEqual(features["features"][0]["properties"], {})

    def assert_state(self, document, code, status=422):
        self.stored_property(None)
        with self.assertRaises(PreviewError) as raised:
            gml_features(parse_xml(document.encode("utf-8")), None)
        self.assertEqual((raised.exception.code, raised.exception.status), (code, status))

    def test_an_unsupported_geometry_is_answered_with_the_format_state(self):
        self.assert_state(collection(member("<gml:Solid/>")), "format")

    def test_a_foreign_crs_is_answered_with_the_crs_state(self):
        self.assert_state(collection(member(
            '<gml:Point srsName="urn:ogc:def:crs:EPSG::25832">'
            '<gml:pos>52.1 13.2</gml:pos></gml:Point>')), "crs")

    def test_a_response_over_the_feature_limit_is_answered_as_upstream(self):
        members = [member(f"<gml:Point><gml:pos>52.{count} 13.{count}</gml:pos></gml:Point>",
                          identifier=f'gml:id="ms.{count}"') for count in range(501)]
        self.assert_state(collection(*members), "limit", 502)

    def test_an_entity_of_the_response_is_never_read(self):
        """The safe parser keeps a reference unresolved and the converter refuses that content."""
        document = ('<!DOCTYPE wfs:FeatureCollection [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                    f'<wfs:FeatureCollection {WFS_NS} {GML_NS}><wfs:member>'
                    '<ms:Feature gml:id="ms.1"><ms:geom>&x;</ms:geom></ms:Feature>'
                    '</wfs:member></wfs:FeatureCollection>')
        root = parse_xml(document.encode("utf-8"))
        self.assertIn(b"&x;", etree.tostring(root))
        with self.assertRaises(gml.GmlError) as raised:
            gml.feature_collection(root, 250, "ms:geom")
        self.assertEqual(raised.exception.code, "gmlSchema")

    def test_an_exception_report_keeps_the_ogc_state(self):
        with self.assertRaises(PreviewError) as raised:
            parse_xml(f'<wfs:ExceptionReport {WFS_NS} version="2.0.0"/>'.encode("utf-8"))
        self.assertEqual(raised.exception.code, "ogc")
