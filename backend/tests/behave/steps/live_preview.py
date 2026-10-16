from io import BytesIO
from unittest.mock import patch

from behave import given, then
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from guardian.shortcuts import assign_perm
from PIL import Image
from registry.models.harvest import HarvestingJob
from registry.models.service import WebMapService
from registry.models.update import WebMapServiceUpdateJob
from requests import Response


@given('User1 can preview the registered WMS')
def authorize_preview(context):
    service = WebMapService.objects.get(pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3')
    user = get_user_model().objects.get(username='User1')
    assign_perm('view_webmapservice', user, service)
    xml = b'''<WMS_Capabilities version="1.3.0"><Capability><Request><GetMap><Format>image/png</Format></GetMap></Request>
        <Layer><CRS>EPSG:4326</CRS><Name>node1</Name><Layer><Name>node1.1</Name></Layer></Layer></Capability></WMS_Capabilities>'''
    service.xml_backup_file = SimpleUploadedFile('preview.xml', xml)
    service.save()
    service.layers.update(bbox_lat_lon=None, is_active=True)
    image = BytesIO()
    Image.new('RGB', (64, 32), 'green').save(image, 'PNG')
    remote = Response()
    remote.status_code = 200
    remote._content = image.getvalue()
    remote._content_consumed = True
    remote.headers['Content-Type'] = 'image/png'
    remote.url = 'https://registered.example/map'
    mock = patch('requests.sessions.Session.send', return_value=remote)
    context.preview_send = mock.start()
    context.add_cleanup(mock.stop)
    context.preview_counts = (WebMapServiceUpdateJob.objects.count(), HarvestingJob.objects.count())


@then('the live preview creates no update or harvesting jobs')
def assert_no_preview_jobs(context):
    assert context.preview_counts == (WebMapServiceUpdateJob.objects.count(), HarvestingJob.objects.count())


@then('the live preview has not contacted upstream')
def assert_stored_discovery(context):
    context.preview_send.assert_not_called()
