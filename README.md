<img src="https://git.osgeo.org/gitea/hollsandre/MapSkinner/raw/branch/pre_master/structure/static/structure/images/mr_map.png" width="200">

## About
Mr. Map is a service registry for web map services ([WMS](https://www.opengeospatial.org/standards/wms)) 
and web feature services ([WFS](https://www.opengeospatial.org/standards/wfs)) as introduced by the 
Open Geospatial Consortium [OGC](http://www.opengeospatial.org/).

Since most GIS solutions out there are specified on a specific use case or aged without proper support, the need
for an open source, generic geospatial registry system is high.

Mr. Map is currently under development by the central spatial infrastructure of Rhineland-Palatinate 
([GDI-RP](https://www.geoportal.rlp.de/mediawiki/index.php/Zentrale_Stelle_GDI-RP)), Germany.
<img src="https://www.geoportal.rlp.de/static/useroperations/images/logo-gdi.png" width="100">


## Install:

```shell
apt update  
apt install postgis postgresql postgresql-server-dev-all libgdal-dev virtualenv python3-pip curl libgnutls28-dev  

su - postgres -c "psql -q -c 'CREATE DATABASE mapskinner'"  

virtualenv -ppython3 /opt/env  
source /opt/env/bin/activate  
cd /opt/  
git clone https://git.osgeo.org/gitea/hollsandre/MapSkinner  
cd /opt/MapSkinner 
pip install -r requirements.txt  

python manage.py makemigrations service  
python manage.py makemigrations structure  
python manage.py migrate  
```

## Initial setup:
Call the setup command and follow the prompt instructions to generate the system's superuser 
```shell
cd .../MapSkinner
python manage.py setup
```