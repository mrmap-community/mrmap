"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.08.20

"""
import os
import subprocess
import sys
from pathlib import Path

from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "(DEV COMMAND) Performs makemessages, checks for empty translations and after that runs compilemessages"

    def add_arguments(self, parser):
        parser.add_argument('lang', nargs='*', type=str)

    def handle(self, *args, **options):
        langs = options.get("lang", [])
        if 'de' not in langs:
            langs.append('de')
        # process custom languages
        call_command("makemessages", locale=langs)
        ROOT_DIR = os.path.dirname(Path(sys.modules['__main__'].__file__).parent)
        SCRIPT_PATH = os.path.join(ROOT_DIR, 'scripts/check-translations.sh')
        ret = subprocess.call(SCRIPT_PATH)
        if ret != 0:
            self.stdout.write(self.style.ERROR('empty translation found.'))
            sys.exit(1)

        call_command("compilemessages", locale=langs)

        self.stdout.write(self.style.SUCCESS('All translations successfully updated'))
