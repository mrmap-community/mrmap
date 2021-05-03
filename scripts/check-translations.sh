#!/bin/bash
parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd $parent_path

case `grep -zoP 'msgstr "".*\n\n' ../mrmap/locale/de/LC_MESSAGES/django.po >/dev/null; echo $?` in
  0)
    exit 1
    ;;
  1)
    exit 0
    ;;
  *)
    exit 1
    ;;
esac