from django.core.management.base import BaseCommand
from django.utils import timezone
from service.models import Service


class Command(BaseCommand):
    help = 'Removes all update candidates that are older than X days. ' \
           'Default is seven days, if you do not pass any parameter'

    def add_arguments(self, parser):
        parser.add_argument('-ot', '--older-than',
                            type=int,
                            help='Indicates the age of update candidates that will be removed')

    def handle(self, *args, **options):
        older_than = 7
        if options['older-than']:
            older_than = options['older-than']

        elements = Service.objects.filter(last_modified__lte=timezone.localtime()-timezone.timedelta(days=older_than))\
                                  .exclude(is_update_candidate_for=None)

        count = len(elements)
        list_of_ids = []
        for element in elements:
            list_of_ids.append({'md_id': element.is_update_candidate_for.metadata.id})

        elements.delete()

        self.stdout.write('Deleted {} objects older than {} days'.format(count, older_than))
        self.stdout.write('List of id\'s from the metadata elements which had update candidates:\n{}'.format(list_of_ids))
