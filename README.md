<img src="https://git.osgeo.org/gitea/hollsandre/MapSkinner/raw/branch/pre_master/structure/static/structure/images/mr_map.png" width="200">

## About
Mr. Map is a service registry for web map services ([WMS](https://www.opengeospatial.org/standards/wms)) 
and web feature services ([WFS](https://www.opengeospatial.org/standards/wfs)) as introduced by the 
Open Geospatial Consortium [OGC](http://www.opengeospatial.org/).

Since most GIS solutions out there are specified on a specific use case or aged without proper support, the need
for an open source, generic geospatial registry system is high.

Mr. Map is currently under development by the central spatial infrastructure of Rhineland-Palatinate 
([GDI-RP](https://www.geoportal.rlp.de/mediawiki/index.php/Zentrale_Stelle_GDI-RP)), Germany.


<img src="https://www.geoportal.rlp.de/static/useroperations/images/logo-gdi.png" width="200">

## Functionality
The system provides the following functionalities:

* User management
  * Create users and organize them in groups, supporting group hierarchy 
  * Configure group inherited permissions
  * Organize groups in organizations 
* Service management
  * Register web map services in all current versions (1.0.0 - 1.3.0)
  * Register web feature services in all current versions (1.0.0 - 2.0.2)
  * Create automatically organizations from service metadata
  * Generate public links for your registered services (GetCapabilities) to use in any map viewer which supports WMS/WFS imports
* Metadata Editor 
  * Edit describing service metadata such as titles, abstracts, keywords and so on
  * Edit describing metadata for every subelement such as map layers or feature types
  * Reset functionality on every level
* Publisher system
  * Allow other groups to register your services with reference on your organization
  * Revoke the permissions whenever you want 
* Dashboard
  * Have an overview on all newest activities of your groups, all your registered services or 
  pending publisher requests
* Catalogue and API
  * Find services using the catalogue JSON interface 
  * Have reading access to metadata, whole services, layers, organizations or groups
  


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

python manage.py makemigrations
python manage.py migrate  
```

## Initial setup:
Call the setup command and follow the prompt instructions to generate the system's superuser and load default elements
```shell
python manage.py setup
```