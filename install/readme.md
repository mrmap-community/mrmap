Here you find a description of files and script found in the install folder.

1. mapskinner_production_setup.bash

This script will install mapskinner with production settings on your debian10
server. Change your hostname and desired database credentials at the beginning
of the script. Afterwards execute it with "bash mapskinner_production_setup.bash".
There will be some questions prompted.

The script will do the following:
- Install and configure Postgres with minimal rights
- Install and configure Nginx with maximal security
- Install and configure MapSkinner
- Register uwsgi, celery, celery-flower as systemd service:
  You can restart with systemctl restart  uwsgi, celery, celery-flower

2. update_mapskinner.bash

This updates your MapSkinner installation

Usage:
bash update_mapskinner.bash

3. mass_register.py

Used to register a list of services at once
This will fail if there are too many, i have to investigate more on this
The list has to contain one wms get capabilities request each line including parameters

You have to temporarily disable csrf verification for the time of registering, do this with:

-sed -i s/"    'django.middleware.csrf.CsrfViewMiddleware',"/"    #'django.middleware.csrf.CsrfViewMiddleware',"/g /opt/MapSkinner/MapSkinner/settings.py
-systemctl restart uwsgi

Afterwards enable again with:

-sed -i s/"    'django.middleware.csrf.CsrfViewMiddleware',"/"    #'django.middleware.csrf.CsrfViewMiddleware',"/g /opt/MapSkinner/MapSkinner/settings.py
-systemctl restart uwsgi

Usage:
Change credentials in mass_register.py then
python3 mass_register.py WMSLIST
