# MapSkinner

New Geoportal project

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