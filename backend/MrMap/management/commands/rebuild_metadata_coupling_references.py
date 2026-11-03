""" Rebuild the derived coupling reference index from the stored xml.

    The index which :class:`registry.models.metadata.MetadataCouplingReference`
    keeps regenerates itself whenever a service metadata record is saved. This
    command repeats the rebuild from the existing stored documents of all or
    selected records: after a restore, after an index change or as a repair
    instrument - without a reharvest.
"""
from django.core.management import BaseCommand
from registry.models.metadata import (MetadataCouplingReference,
                                      ServiceMetadataRecord)


class Command(BaseCommand):
    help = ("Rebuilds the derived coupling references of harvested service "
            "metadata records from their stored xml.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--id", type=int, action="append", dest="ids",
            help="Only rebuild the service metadata records with this id; "
                 "repeatable. Without the option all records are rebuilt.")

    def handle(self, *args, **options):
        records = ServiceMetadataRecord.objects.all()
        ids = options.get("ids")
        if ids:
            records = records.filter(pk__in=ids)

        rebuilt = 0
        references = 0
        for record in records.iterator():
            rows = MetadataCouplingReference.objects.rebuild_for(record)
            rebuilt += 1
            references += len(rows)

        self.stdout.write(self.style.SUCCESS(
            f"rebuilt {references} coupling references for {rebuilt} "
            f"service metadata records"))
