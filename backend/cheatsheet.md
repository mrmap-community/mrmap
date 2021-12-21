
# send messages via websocket

root@mrmap-backend:/opt/mrmap# python3 manage.py shell_plus

>>> from channels.layers import get_channel_layer
>>> from asgiref.sync import async_to_sync
>>> async_to_sync(get_channel_layer().group_send)("default", {"type": "send.msg", "json": {"hello": "world"}})

event: created | update | delete

{
    'event': 'update',
    'jsonapi': {
        'data': {
            'type': 'TaskResult',
            'id': '1',
            'attributes': {
                'taskId': '958c2b95-ea2c-44a6-b15e-f14a0c2faa53',
                'taskName': 'registry.tasks.service.build_ogc_service',
                'taskArgs': '"()"',
                'taskKwargs': '"{'get_capabilities_url': 'https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities', 'collect_metadata_records': True, 'service_auth_pk': None, 'current_user': UUID('682394e5-fd2f-4284-a410-54f302425171')}"',
                'status': 'SUCCESS',
                'worker': 'mrmap-celery-default-worker',
                'contentType': 'application/json',
                'contentEncoding': 'utf-8',
                'result': '{"data": {"type": "OgcService", "id": "4da6ba1d-c400-43c6-8cc0-9625423213dd", "links": {"self": "/api/v1/registry/ogcservices/4da6ba1d-c400-43c6-8cc0-9625423213dd/"}}, "meta": {"collect_metadata_records_job_id": "f8fab3e5-8926-42ce-bd87-eb59bc24b489"}}',
                'dateCreated': 'Dec. 14, 2021, 8:07 p.m.',
                'dateDone': 'Dec. 14, 2021, 8:07 p.m.',
                'traceback': '',
                'task_meta': '{"children": [[["f8fab3e5-8926-42ce-bd87-eb59bc24b489", null], [[["624cedd7-cf63-4b61-b061-d438d77e3183", null], null], [["c3ad69dc-8982-4cda-8aab-11218d8468e3", null], null], [["5726ce1b-0a84-4c5a-8c3a-43dee2c80dee", null], null], [["9bb3a0ae-de98-4067-a9ee-fc79a905278b", null], null], [["494ff58b-f49b-4ed6-aeb3-34d509aa89c5", null], null], [["07cbbbcb-7797-41ba-b7b0-0c075fa36312", null], null]]]]}'
            }
        }
    }
}


async_to_sync(get_channel_layer().group_send)("default", {"type": "send.msg", "json": {'type': 'taskResults/add', 'payload': {'type': 'TaskResult', 'id': '1234', 'attributes': {'taskId': '958c2b95-ea2c-44a6-b15e-f14a0c2faa53', 'status': 'STARTED', 'task_meta': {'done': 0, 'total': '1', 'phase': 'fetching remote document...'}}}}})




{'payload': {'type': 'TaskResult', 'id': '1', 'attributes': {'result': {}, 'task_meta': {}, 'task_id': '123', 'task_name': None, 'task_args': None, 'task_kwargs': None, 'status': 'PENDING', 'worker': None, 'content_type': '', 'content_encoding': '', 'date_created': '2021-12-21T09:15:34.813060+01:00', 'date_done': '2021-12-21T09:15:34.813088+01:00', 'traceback': None}, 'links': {'self': 'http://testserver/api/v1/notify/task-results/1/'}}, 
'type': 'taskResults/add'}

{'payload': {'type': 'TaskResult', 'id': '1', 'attributes': {'task_id': '123', 'task_name': '', 'task_args': '', 'task_kwargs': '', 'status': 'PENDING', 'worker': '', 'content_type': '', 'content_encoding': '', 'result': '', 'date_created': '2021-12-21 08:15:34.813060+00:00', 'date_done': '2021-12-21 08:15:34.813088+00:00', 'traceback': '', 'task_meta': ''}},
'type': 'taskResults/add'}