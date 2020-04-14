Brief description of files and scripts found in the install folder.

I.  mapskinner_production_setup.bash

This script will install mapskinner with production settings on your blank debian10  
server. Get it with:  
```wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/mapskinner_production_setup.bash```  
Change your hostname and desired database credentials at the beginning of the script.  
Afterwards execute it with:  
```bash mapskinner_production_setup.bash```  
There will be some questions prompted.  

The script will do the following:   
- Install and configure Postgres with minimal rights
- Install and configure Nginx with maximal security
- Install and configure MapSkinner
- Register uwsgi, celery, celery-flower as systemd service:  
  You can restart them with systemctl restart  uwsgi, celery, celery-flower   
- Configuration files can be found in the conf folder, they are altered   
  during install if needed and placed at the following locations:  
  - /etc/nginx/conf.d/mrmap.conf -> Site conf for MrMap  
  - /opt/MapSkinner/MapSkinner/mrmap_uwsgi.ini -> uwsgi ini file  
  - /etc/systemd/system/uwsgi.service -> Systemd config for uwsgi server  
  - /etc/systemd/system/celery.service -> Systemd config for celery  
  - /etc/default/celery -> Environment file for  celery  

At the end of the script you are asked if you would like to install ModSecurity and generate  
stronger encryption keys, this is absolutely recommended for a real production server  
facing the threats of the www, it can take up to an hour though! Can be skipped for testing and  
intranet only servers.  


II.  update_mapskinner.bash

This updates your MapSkinner installation.  
Get it with:
```wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/update_mapskinner.bash```   

Usage:  
bash update_mapskinner.bash  

III. mass_register.py

Used to register a list of services at once  .
This will fail if there are too many, i have to investigate more on this  .
The list has to contain one wms get capabilities request each line including parameters   .

You have to temporarily disable csrf verification for the time of registering, do this with:  

```
-sed -i s/"    'django.middleware.csrf.CsrfViewMiddleware',"/"    #'django.middleware.csrf.CsrfViewMiddleware',"/g /opt/MapSkinner/MapSkinner/settings.py
-systemctl restart uwsgi

Afterwards enable again with:

-sed -i s/"    '#django.middleware.csrf.CsrfViewMiddleware',"/"    'django.middleware.csrf.CsrfViewMiddleware',"/g /opt/MapSkinner/MapSkinner/settings.py
-systemctl restart uwsgi
```

Usage:  
Change credentials in mass_register.py then  
python3 mass_register.py WMSLIST  
