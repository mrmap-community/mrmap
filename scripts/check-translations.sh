python ../mrmap/manage.py dev_messages

case `pcregrep -Mn 'msgstr "".*\n\n' ../mrmap/locale/de/LC_MESSAGES/django.po >/dev/null; echo $?` in
  0)
    echo "empty translation found."
    exit 1
    ;;
  1)
    exit 0
    ;;
  *)
    echo "something went wrong."
    exit 1
    ;;
esac