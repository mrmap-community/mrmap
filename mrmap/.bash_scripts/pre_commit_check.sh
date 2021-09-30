#!/bin/bash

echo "Validating PEP8 compliance..."
pycodestyle --ignore=W504,E501 mrmap/

echo "Validating model changes that are not migrated..."
python /opt/mrmap/manage.py makemigrations --check --dry-run

echo "Validating for empty translations..."
#python /opt/mrmap/manage.py makemessages --locale=de
/opt/mrmap/.bash_scripts/check_translations.sh

echo "Validating if compiled message file is not up to date..."
if [[ /opt/mrmap/locale/de/LC_MESSAGES/django.po -nt /opt/mrmap/locale/de/LC_MESSAGES/django.mo ]]; then
  exit 1;
fi
