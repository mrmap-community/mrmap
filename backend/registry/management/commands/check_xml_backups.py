"""Report metadata records whose stored xml_backup document is gone (#1150).

The metadata records of the catalogue answer their document from a *file* of
the media storage which the record row only references. #1150 measured a
large share of the demo corpus pointing at a file which is not there --
spread uniformly over every import epoch, so whatever created the orphans is
systematic and not a one-time storage incident. Every ``/csw`` GetRecords
page which contains such a record is refused with ``DocumentUnavailable``,
which at the observed density makes the corpus practically unpageable; the
record detail views read the same file.

This command is the operator-facing answer to the damage itself: it walks the
three metadata record tables, asks the storage behind ``xml_backup_file``
whether each named file is there, and reports the rows which name a file that
is not. It reads nothing of the document and changes nothing -- restoring or
re-harvesting the reported records stays with the operator. The exit code is
1 when orphans were found, so the check can run as a cron or monitoring probe
and the sum per table is the number that probe graphs.
"""

from django.core.management.base import BaseCommand

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      ServiceMetadataRecord)

# the three metadata record tables whose documents /csw serves; each carries
# the xml_backup_file of DocumentModelMixin
RECORD_MODELS = {
    'dataset': DatasetMetadataRecord,
    'service': ServiceMetadataRecord,
    'application': ApplicationMetadataRecord,
}


class Command(BaseCommand):
    help = ("Report metadata records whose xml_backup_file names a file which "
            "is not in the media storage -- the records which make every /csw "
            "page that contains one fail with DocumentUnavailable (#1150). "
            "Reads nothing and changes nothing; exits 1 when orphans were "
            "found, so it can run as a monitoring probe.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--model', choices=sorted(RECORD_MODELS) + ['all'],
            default='all',
            help='check only this metadata record table (default: all three)')
        parser.add_argument(
            '--limit', type=int, default=10,
            help='how many orphans per table are listed with their '
                 'identifier (default 10; 0 reports the counts only)')

    def handle(self, *args, **options):
        models = (RECORD_MODELS if options['model'] == 'all'
                  else {options['model']: RECORD_MODELS[options['model']]})

        total_checked = 0
        total_missing = 0
        for name, model in models.items():
            storage = model._meta.get_field('xml_backup_file').storage
            checked = 0
            missing = []
            # only the columns the check needs, streamed: the corpus is six
            # hundred thousand rows and the check runs beside production traffic
            for pk, file_identifier, file_name in (
                    model.objects
                    .order_by('pk')
                    .values_list('pk', 'file_identifier', 'xml_backup_file')
                    .iterator(chunk_size=2000)):
                checked += 1
                if not self.file_is_there(storage, file_name):
                    missing.append((pk, file_identifier, file_name))

            total_checked += checked
            total_missing += len(missing)
            self.stdout.write(
                f"{name}: {checked} records checked, "
                f"{len(missing)} without a stored document")
            self.report_orphans(missing, options['limit'])

        if total_missing:
            self.stdout.write(self.style.WARNING(
                f"{total_checked} records checked, {total_missing} orphaned"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"{total_checked} records checked, "
                "every stored document is there"))

        if total_missing:
            raise SystemExit(1)

    @staticmethod
    def file_is_there(storage, file_name):
        """Whether the storage holds the file which the row names.

        An empty name is as unservable as a missing file -- the record can
        never answer its document -- and a storage which cannot even answer
        the question about a name (a name it rejects, a backend which fails)
        is reported as missing rather than killing the whole sweep.
        """
        if not file_name:
            return False
        try:
            return storage.exists(file_name)
        except (OSError, ValueError):
            return False

    def report_orphans(self, missing, limit):
        for pk, file_identifier, file_name in missing[:limit]:
            self.stdout.write(
                f"  pk={pk} identifier={file_identifier} file={file_name or '(empty)'}")
        if len(missing) > limit:
            self.stdout.write(f"  ... and {len(missing) - limit} more")
