#!/bin/bash

# Ignored violations:
#
#   W504: Line break after binary operator
#   E501: Line too long

exec 1>&2

EXIT=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NOCOLOR='\033[0m'


echo "Validating PEP8 compliance..."
flake8 --ignore E501,W504 /opt/mrmap/

if [ $? != 0 ]; 
then
	EXIT=1
  printf "${RED}PEP8 comliance FAILED${NOCOLOR}\n"
else
  printf "${GREEN}PEP8 comliance SUCCESS${NOCOLOR}\n"
fi

echo "Validating model changes that are not migrated..."
python /opt/mrmap/manage.py makemigrations --check --dry-run

if [ $? != 0 ]; 
then
	EXIT=1
  printf "${RED}pending migrations found${NOCOLOR}\n"
else
  printf "${GREEN}no pending migrations found${NOCOLOR}\n"
fi

echo "Validating for empty translations..."
python /opt/mrmap/manage.py makemessages --locale=de

if [ $? != 0 ]; 
then
	EXIT=1
  printf "${RED}makemessages failed${NOCOLOR}\n"
else
  printf "${GREEN}makemessages SUCCESS${NOCOLOR}\n"
fi

/opt/mrmap/.bash_scripts/check_translations.sh

if [ $? != 0 ]; 
then
	EXIT=1
  printf "${RED}empty translations where found${NOCOLOR}\n"
else
  printf "${GREEN}no empty translations where found${NOCOLOR}\n"
fi

echo "Validating if compiled message file is not up to date..."
if [[ /opt/mrmap/locale/de/LC_MESSAGES/django.po -nt /opt/mrmap/locale/de/LC_MESSAGES/django.mo ]]; 
then
  EXIT=1;
  printf "${RED}django.mo translation file is not up to date${NOCOLOR}\n"
else
  printf "${GREEN}django.mo translation file is up to date${NOCOLOR}\n"
fi

exit $EXIT