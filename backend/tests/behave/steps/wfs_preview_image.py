import json
from io import BytesIO
from unittest.mock import patch

from behave import given, then
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from guardian.shortcuts import assign_perm
from PIL import Image
from registry.models.harvest import HarvestingJob
from registry.models.service import WebFeatureService
from registry.models.update import WebFeatureServiceUpdateJob
from requests import Response


@given('the registered WFS has an automatic image preview')
def prepare_wfs_thumbnail(context):
    service = WebFeatureService.objects.get(pk='9cc4889d-0cd4-4c3b-8975-58de6d30db41')
    user = get_user_model().objects.get(username='User1')
    assign_perm('view_webfeatureservice', user, service)
    capabilities = b'''<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0"
        xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink"
        xmlns:ms="https://example.test/ms" version="2.0.0">
        <ows:OperationsMetadata><ows:Operation name="GetFeature">
        <ows:DCP><ows:HTTP><ows:Get xlink:href="https://registered.example/features"/></ows:HTTP></ows:DCP>
        <ows:Parameter name="outputFormat"><ows:AllowedValues><ows:Value>application/json</ows:Value>
        </ows:AllowedValues></ows:Parameter></ows:Operation></ows:OperationsMetadata>
        <wfs:FeatureTypeList><wfs:FeatureType><wfs:Name>wfs1-node1</wfs:Name>
        <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
        <ows:WGS84BoundingBox><ows:LowerCorner>-2 0</ows:LowerCorner><ows:UpperCorner>4 8</ows:UpperCorner>
        </ows:WGS84BoundingBox></wfs:FeatureType></wfs:FeatureTypeList></wfs:WFS_Capabilities>'''
    service.xml_backup_file = SimpleUploadedFile('wfs-thumbnail.xml', capabilities)
    service.is_active = True
    service.save()
    service.featuretypes.update(is_active=True)
    remote = Response()
    remote.status_code = 200
    remote._content = json.dumps({
        'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {}, 'geometry': {'type': 'Point', 'coordinates': [1, 2]}}
        ]
    }).encode()
    remote._content_consumed = True
    remote.headers['Content-Type'] = 'application/json'
    remote.url = 'https://registered.example/features'
    mock = patch('requests.sessions.Session.send', return_value=remote)
    context.wfs_thumbnail_send = mock.start()
    context.add_cleanup(mock.stop)
    context.wfs_thumbnail_counts = (WebFeatureServiceUpdateJob.objects.count(), HarvestingJob.objects.count())


@then('the WFS preview is a bounded PNG image')
def assert_wfs_thumbnail(context):
    assert context.response['Content-Type'] == 'image/png'
    assert context.response['Cache-Control'] == 'no-store'
    with Image.open(BytesIO(context.response.content)) as image:
        assert image.format == 'PNG'
        assert image.size == (512, 256)
    context.wfs_thumbnail_send.assert_called_once()


@then('the WFS preview creates no update or harvesting jobs')
def assert_no_thumbnail_jobs(context):
    assert context.wfs_thumbnail_counts == (WebFeatureServiceUpdateJob.objects.count(), HarvestingJob.objects.count())


@then('the WFS thumbnail has not contacted upstream')
def assert_no_thumbnail_upstream(context):
    context.wfs_thumbnail_send.assert_not_called()
