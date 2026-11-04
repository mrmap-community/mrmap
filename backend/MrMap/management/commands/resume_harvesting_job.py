"""Resume a harvest whose import backlog is stranded behind a task id which
outlived its message (#972).

Before this command existed, the only way past such a shadow was hand-deleting
rows from ``registry_harvestingjobtaskid`` or calling
``call_chord_md_metadata_file_to_db`` raw - both invisible in the UI. This is
the one supported path: it asks the broker the same question the worker-restart
recovery asks, resumes through the same code the recovery resumes through, and
writes what it decided to the harvesting log so the harvesting card tells it.
While a message of the registered run verifiably still lives on the broker it
refuses - resuming then would publish the backlog a second time onto the queue
which is already consuming it (#891).
"""

from django.core.management.base import BaseCommand

from registry.enums.harvesting import HarvestingPhaseEnum


class Command(BaseCommand):
    help = ("Resume a harvesting job which waits in 'records to db': when the broker "
            "holds no message of the run its task ids register, drop that shadow and "
            "publish the waiting records as a new import chord, visibly on the job. "
            "Refuses while a message of that run could still be consumed (#972).")

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int, help="the id of the harvesting job")

    def handle(self, *args, **options):
        # the tasks import the models inside their functions to avoid circular
        # import errors; this command speaks on their behalf
        from registry.models.harvest import HarvestingJob
        from registry.tasks.harvest import (import_run_message_state,
                                            resume_stale_import_run)

        job = HarvestingJob.objects.filter(pk=options["job_id"]).first()
        if job is None:
            self.stderr.write(self.style.ERROR(
                f"there is no harvesting job with id {options['job_id']}"))
            raise SystemExit(1)
        if job.done_at is not None:
            self.stderr.write(self.style.ERROR(
                f"harvesting job {job.pk} ended; there is no backlog to resume"))
            raise SystemExit(1)
        if job.phase != HarvestingPhaseEnum.RECORDS_TO_DB.value:
            self.stderr.write(self.style.ERROR(
                f"harvesting job {job.pk} is in phase "
                f"'{HarvestingPhaseEnum(job.phase).label}', not 'records to db'; "
                "a stranded download resumes through the worker restart recovery, "
                "this command only resumes the import"))
            raise SystemExit(1)

        registered = {
            str(_id) for _id in
            job.celery_task_ids.filter(creation=False).values_list("task_id", flat=True)}
        state = import_run_message_state(registered) if registered else False
        if state is True:
            self.stderr.write(self.style.ERROR(
                f"the broker still holds a message of the run job {job.pk} registered; "
                "its backlog is being consumed and must not be published a second "
                "time - see the harvesting log of the job for what recovery logged"))
            raise SystemExit(1)
        if state is None:
            self.stderr.write(self.style.ERROR(
                f"the broker could not be asked whether the run of job {job.pk} is "
                "still live; nothing was published - fix the broker connection and "
                "run this command again"))
            raise SystemExit(1)

        published = resume_stale_import_run(
            job, registered, origin="manage.py resume_harvesting_job")
        if published:
            self.stdout.write(self.style.SUCCESS(
                f"harvesting job {job.pk}: {len(registered)} registered task ids name no "
                "message on the broker; the waiting records were published as a new "
                "import chord and the job carries the harvesting log entry of it"))
        else:
            # #970: the stale shadow is gone but the chord did not go out, so
            # the operator is told which of the two waits it is, not lied to
            self.stdout.write(self.style.WARNING(
                f"harvesting job {job.pk}: {len(registered)} registered task ids name "
                "no message on the broker and their rows are gone, but the import "
                "chord was not published: either a publish of it still waits on the "
                "broker and rebuilds the chord when consumed, or the broker could "
                "not answer and the publish stays declined to keep the backlog "
                "single - the harvesting log of the job says which"))
