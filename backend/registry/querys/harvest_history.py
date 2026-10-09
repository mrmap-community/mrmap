"""Record catalogue removals only after a complete, successful snapshot."""
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum, HarvestingPhaseEnum, LogLevelEnum


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
    if not job.service_id:
        return
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
