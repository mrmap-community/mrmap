"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.09.20

"""
from time import time

from django.core.management import BaseCommand
from django.db import transaction

from service.helper.enums import MetadataRelationEnum, MetadataEnum
from service.models import Metadata


class Command(BaseCommand):
    help = "(DEV COMMAND) Deletes all harvested metadata."

    def add_arguments(self, parser):
        parser.add_argument('csw_id', nargs='*', type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        csw_id = options.get(
            "csw_id",
            None
        )
        if csw_id is None or len(csw_id) == 0:
            csw_id = Metadata.objects.filter(
                metadata_type=MetadataEnum.CATALOGUE.value
            ).values_list("id", flat=True)
        mds = Metadata.objects.filter(
            related_metadata__relation_type=MetadataRelationEnum.HARVESTED_THROUGH.value,
        )

        t_start = time()
        self.stdout.write(self.style.NOTICE("Found {} records in total. Start removing...".format(mds.count())))
        for _id in csw_id:
            mds_id = mds.filter(
                related_metadata__metadata_to__id=_id
            )
            self.stdout.write(self.style.NOTICE("Found {} records for {}. Start removing...".format(mds_id.count(), _id)))
            for md in mds_id:
                md.delete()
        self.stdout.write(self.style.NOTICE("Removing finished. Took {}s".format(time() - t_start)))
