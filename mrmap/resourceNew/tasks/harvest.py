import random

from celery import shared_task, chain, chord
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from eulxml import xmlmap
from job.tasks import NewJob, CurrentTask
from resourceNew.enums.service import OGCOperationEnum, HttpMethodEnum
from resourceNew.models import DatasetMetadata, Service, OperationUrl
from resourceNew.models.harvest import HarvestResult
from resourceNew.ows_client.request_builder import CatalogueServiceWeb
from resourceNew.parsers.ogc.csw_get_record_response import GetRecordsResponse
from structure.enums import PendingTaskEnum
from time import sleep

MAX_RECORDS_TEST_LIST = [50, 100, 200, 400]


@shared_task(name="async_harvest_service",
             bind=True,
             base=NewJob)
def harvest_service(self,
                    service,
                    **kwargs):
    _calibrate_step_size = chord([get_response_elapsed.s(service, test_max_records, **kwargs) for test_max_records in MAX_RECORDS_TEST_LIST],
                                 calibrate_step_size.s(**kwargs))
    workflow = chain(_calibrate_step_size,
                     schedule_get_records.s(service, **kwargs))
    workflow.apply_async()
    return self.job.pk


@shared_task(name="async_schedule_get_records",
             bind=True,
             base=CurrentTask)
def schedule_get_records(self,
                         step_size,
                         service_id,
                         **kwargs):
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url", flat=True).get(service__id=service_id,
                                                                             operation=OGCOperationEnum.GET_RECORDS.value,
                                                                             method=HttpMethodEnum.GET.value)
    remote_service = CatalogueServiceWeb(base_url=get_records_url,
                                         version=db_service.service_version)
    request = remote_service.get_get_records_request(**{remote_service.TYPE_NAME_QP: "gmd:MD_Metadata",
                                                        remote_service.OUTPUT_SCHEMA_QP: "http://www.isotc211.org/2005/gmd",
                                                        remote_service.RESULT_TYPE_QP: "hits"})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())

    get_records_xml = xmlmap.load_xmlobject_from_string(string=response.content,
                                                        xmlclass=GetRecordsResponse)
    max_records = get_records_xml.total_records
    round_trips = (max_records // step_size)
    if max_records % step_size > 0:
        round_trips += 1

    progress_step_size = 100 / round_trips

    if self.task:
        self.task.phase = f"collecting {max_records} records with step size {step_size} in {round_trips} requests: 0/{round_trips}"
        self.task.save()

    get_record_tasks = []
    for round_trip in range(round_trips):
        start_position = round_trip * step_size + 1
        get_record_tasks.append(get_records.s(service_id, max_records, step_size, start_position, progress_step_size, **kwargs))
    header = get_record_tasks
    callback = analyze_results.s(service_id, max_records, **kwargs)
    chord(header)(callback)


@shared_task(name="async_calibrate_step_size")
def calibrate_step_size(test_results,
                        **kwargs):
    best_result = None
    for _step_size, elapsed_time in test_results:
        if not best_result:
            best_result = _step_size, elapsed_time
        else:
            if best_result[1] == -1:
                # The used step_size runs in an error. So we can't use it.
                continue
            if elapsed_time >= 2 * best_result[1]:
                break
            else:
                best_result = _step_size, elapsed_time
    return best_result[0]


@shared_task(name="async_get_response_elapse",
             bind=True,
             base=CurrentTask)
def get_response_elapsed(self,
                         service_id,
                         test_max_records,
                         **kwargs):
    if self.task:
        self.task.status = PendingTaskEnum.STARTED.value
        self.task.phase = f"Start analyzing elapsing time of the request for maxRecords query parameter '{test_max_records}'"
        self.task.save()
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url", flat=True).get(service__id=service_id,
                                                                             operation=OGCOperationEnum.GET_RECORDS.value,
                                                                             method=HttpMethodEnum.GET.value)
    remote_service = CatalogueServiceWeb(base_url=get_records_url,
                                         version=db_service.service_version)
    request = remote_service.get_get_records_request(**{remote_service.TYPE_NAME_QP: "gmd:MD_Metadata",
                                                        remote_service.OUTPUT_SCHEMA_QP: "http://www.isotc211.org/2005/gmd",
                                                        remote_service.RESULT_TYPE_QP: "results",
                                                        remote_service.MAX_RECORDS_QP: test_max_records,
                                                        remote_service.START_POSITION_QP: 1})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())
    get_records_xml = xmlmap.load_xmlobject_from_string(string=response.content,
                                                        xmlclass=GetRecordsResponse)
    try:
        if isinstance(get_records_xml.total_records, int) and isinstance(get_records_xml.returned_records, int):
            pass
        elapsed = response.elapsed.total_seconds()
    except:
        elapsed = -1

    if self.task:
        self.task.status = PendingTaskEnum.SUCCESS.value
        self.task.phase = f"Elapsing time for maxRecords query parameter '{test_max_records}': {elapsed}"
        self.task.progress = 100
        self.task.save()
    return test_max_records, elapsed


@shared_task(name="async_get_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def get_records(self,
                service_id,
                max_records,
                step_size,
                start_position,
                progress_step_size,
                **kwargs):
    sleep(random.uniform(0.1, 0.9))
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url", flat=True).get(service__id=service_id,
                                                                             operation=OGCOperationEnum.GET_RECORDS.value,
                                                                             method=HttpMethodEnum.GET.value)
    remote_service = CatalogueServiceWeb(base_url=get_records_url,
                                         version=db_service.service_version)
    request = remote_service.get_get_records_request(**{remote_service.TYPE_NAME_QP: "gmd:MD_Metadata",
                                                        remote_service.OUTPUT_SCHEMA_QP: "http://www.isotc211.org/2005/gmd",
                                                        remote_service.RESULT_TYPE_QP: "results",
                                                        remote_service.MAX_RECORDS_QP: step_size,
                                                        remote_service.START_POSITION_QP: start_position})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())

    content_type = response.headers.get("content-type")
    if "/" in content_type:
        content_type = content_type.split("/")[-1]
    result = HarvestResult.objects.create(service=Service.objects.get(id=service_id),
                                          job=self.task.job)
    result.result_file.save(name=f'{start_position}_to_{start_position + step_size - 1}_of_{max_records}.{content_type}',
                            content=ContentFile(response.text))
    if self.task:
        # CAREFULLY!!!: this is a race condition in parallel execution, cause all tasks will waiting for the task
        # which looks the pending task for updating progress and phase.
        with transaction.atomic():
            cls = self.task.__class__
            task = cls.objects.select_for_update().get(pk=self.task.pk)
            if not task.started_at:
                task.started_at = timezone.now()
            task.status = PendingTaskEnum.STARTED.value
            task.progress += progress_step_size / 2
            try:
                phase = task.phase.split(":")
                current_phase = phase[0]
                phase_steps = phase[-1].split("/")

                task.phase = f"{current_phase}: {int(phase_steps[0]) + 1}/{phase_steps[-1]}"
            except Exception:
                pass
            task.save()
    return result.pk


@shared_task(name="async_analyze_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def analyze_results(self,
                    harvest_results,
                    service_id,
                    total_records,
                    **kwargs):
    if self.task:
        self.task.status = PendingTaskEnum.STARTED.value
        self.task.phase = f"Persisting downloaded records: 0 / {total_records}"
        self.task.save()
    service = Service.objects.get(pk=service_id)
    results = HarvestResult.objects.filter(id__in=harvest_results)
    dataset_list = []
    progress_step_size = 100 / total_records / 2

    for result in results:
        xml = result.parse()
        for md_metadata in xml.records:
            if self.task:
                self.task.progress += progress_step_size
                try:
                    phase = self.task.phase.split(":")
                    current_phase = phase[0]
                    phase_steps = phase[-1].split("/")
                    self.task.phase = f"{current_phase}: {int(phase_steps[0]) + 1}/{phase_steps[-1]}"
                except Exception:
                    pass
                self.task.save()
            try:
                if md_metadata.hierarchy_level == "dataset":
                    dataset = DatasetMetadata.iso_metadata.create_from_parsed_metadata(parsed_metadata=md_metadata,
                                                                                       related_object=service,
                                                                                       origin_url=None)
                    dataset_list.append(dataset.pk)
            except Exception as e:
                # todo: log the exception
                pass

    if self.task:
        self.task.status = PendingTaskEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{DatasetMetadata.get_table_url()}?id__in={",".join(str(pk) for pk in dataset_list)}">dataset metadata</a>'
        self.task.save()
    return dataset_list
