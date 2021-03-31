"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.08.20

"""
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "(DEV COMMAND) Performs makemessages and compilemessages"

    def add_arguments(self, parser):
        parser.add_argument('lang', nargs='*', type=str)

    def handle(self, *args, **options):
        langs = options.get("lang", [])
        if 'de' not in langs:
            langs.append('de')
        # process custom languages
        call_command("makemessages", locale=langs)
        call_command("compilemessages", locale=langs)
