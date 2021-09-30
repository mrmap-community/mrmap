#!/bin/bash
case `grep -zoP 'msgstr "".*\n\n' /opt/mrmap/locale/de/LC_MESSAGES/django.po >/dev/null; echo $?` in
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