"""What the completed harvests of a catalogue tell about that catalogue.

Removals of records are recorded only after a complete, successful snapshot, and
the duration a harvest takes is measured by the runs which finished: both
questions are answered by the runs a catalogue already has behind it.
"""
from django.db import transaction
from django.db.models import (Avg, Count, DateTimeField, DurationField, Exists,
                              ExpressionWrapper, F, Max, OuterRef, Q, Subquery)
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from notify.enums import ProcessStatusEnum
from registry.enums.harvesting import (CollectingStatenEnum,
                                       HarvestingPhaseEnum, LogLevelEnum)


PRESENT_STATES = [CollectingStatenEnum.NEW, CollectingStatenEnum.UPDATED,
                  CollectingStatenEnum.EXISTING]


def complete_snapshots(service_id):
    from registry.models.harvest import HarvestingJob, HarvestingLog, TemporaryMdMetadataFile
    present = Q(harvested_metadata_relation__collecting_state__in=PRESENT_STATES)
    return HarvestingJob.objects.filter(
        service_id=service_id, harvest_datasets=True, harvest_services=True,
        phase=HarvestingPhaseEnum.COMPLETED, done_at__isnull=False,
        total_records__isnull=False,
    ).annotate(
        dataset_count=Count('harvested_metadata_relation__dataset_metadata_record', filter=present, distinct=True),
        service_count=Count('harvested_metadata_relation__service_metadata_record', filter=present, distinct=True),
    ).filter(
        total_records=F('dataset_count') + F('service_count'),
    ).filter(
        ~Exists(HarvestingLog.objects.filter(harvesting_job_id=OuterRef('pk'), level__lte=LogLevelEnum.ERROR)),
        ~Exists(TemporaryMdMetadataFile.objects.filter(job_id=OuterRef('pk'), has_import_error=True)),
    )


def harvest_durations(service_ids):
    """How long a harvest of a catalogue takes, measured by the runs which finished.

    A schedule which fires more often than a harvest takes is a no-op on paper
    and load on the remote catalogue (#693). Only the runs which finished answer
    how long the work of a harvest is: a run which was aborted or stayed
    incomplete stopped at a moment which says nothing about a complete harvest.

    The duration of a run is the time between its end and the moment it was made.
    `date_created` is nullable and only set explicitly (see ProcessingData), so
    the creation of a run is read from the first row of its change log - the same
    source which answers who made a run. A catalogue which never finished a
    harvest answers no row, so an invented estimate cannot be mistaken for a
    measured one.

    Args:
        service_ids: the catalogues to answer the durations of

    Returns:
        dict: the row of every catalogue which finished a harvest, keyed by its
            id, each naming the average duration of its runs and the end of the
            newest of them
    """
    from registry.models.harvest import HarvestingJob
    created_at = Coalesce(
        F('date_created'),
        Subquery(
            HarvestingJob.change_log.model.objects
            .filter(history_relation_id=OuterRef('pk'))
            .order_by('history_date', 'history_id')
            .values('history_date')[:1],
            output_field=DateTimeField()))
    return {
        row['service']: row
        for row in HarvestingJob.objects.filter(
            service_id__in=service_ids,
            phase=HarvestingPhaseEnum.COMPLETED,
            done_at__isnull=False,
        ).values('service').annotate(
            average=Avg(ExpressionWrapper(
                F('done_at') - created_at, output_field=DurationField())),
            last_done=Max('done_at'))
    }


@transaction.atomic
def complete_harvest(job_id):
    from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
    job = HarvestingJob.objects.select_for_update().get(pk=job_id)
    # A late chord callback must never turn an aborted harvest into a snapshot.
    if job.phase in [HarvestingPhaseEnum.ABORT, HarvestingPhaseEnum.ABORTED, HarvestingPhaseEnum.COMPLETED]:
        return
    job.phase = HarvestingPhaseEnum.COMPLETED
    job.done_at = now()
    job.save(skip_history_when_saving=False)
    job.report_process(
        ProcessStatusEnum.COMPLETED,
        phase=str(HarvestingPhaseEnum.COMPLETED.label))
    if not job.service_id:
        return
    # the size which completed this run is the size the next run of this catalogue starts with, so
    # the catalogue keeps the memory of what its remote service answers (#691). Answered by an
    # update of the row: a harvest which finished is no edit an administrator has to answer with a
    # new version of the catalogue.
    from registry.models.service import CatalogueService
    CatalogueService.objects.filter(pk=job.service_id).exclude(
        max_step_size=job.max_step_size).update(
        max_step_size=job.max_step_size)
    snapshots = complete_snapshots(job.service_id)
    if not snapshots.filter(pk=job.pk).exists():
        return
    # date_created is nullable and only set explicitly (see ProcessingData), so
    # jobs created by HarvestingJobManager come without it. Fall back to this
    # job's own completion time, which is always set above, instead of querying
    # with None - Django rejects that with "Cannot use None as a query value".
    previous_snapshot_boundary = job.date_created or job.done_at
    previous = snapshots.exclude(pk=job.pk).filter(
        done_at__lte=previous_snapshot_boundary).order_by('-done_at', '-pk').first()
    if previous is None:
        return
    current = HarvestedMetadataRelation.objects.filter(harvesting_job=job, collecting_state__in=PRESENT_STATES)
    prior = HarvestedMetadataRelation.objects.filter(harvesting_job=previous, collecting_state__in=PRESENT_STATES)
    for field in ['dataset_metadata_record_id', 'service_metadata_record_id']:
        missing = prior.filter(**{f'{field}__isnull': False}).exclude(
            **{f'{field}__in': current.filter(**{f'{field}__isnull': False}).values(field)}
        ).values_list(field, flat=True).distinct()
        batch = []
        for record_id in missing.iterator(chunk_size=1000):
            batch.append(HarvestedMetadataRelation(harvesting_job=job, collecting_state=CollectingStatenEnum.REMOVED, **{field: record_id}))
            if len(batch) == 1000:
                HarvestedMetadataRelation.objects.bulk_create(batch)
                batch = []
        if batch:
            HarvestedMetadataRelation.objects.bulk_create(batch)
