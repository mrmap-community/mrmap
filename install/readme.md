Brief description of files and scripts found in the install folder.

**I.    mapskinner_production_setup.bash**

This script will install MrMap with production settings on your blank debian10 server.  

Get it with:
```
wget https://git.osgeo.org/gitea/GDI-RP/MrMap/raw/branch/pre_master/install/mrmap_production_setup.bash
```  

Change your hostname and desired database credentials at the beginning of the script. Make the script executable.

Afterwards execute it with:  
```
sudo bash mrmap_production_setup.bash
```  


There will be some questions prompted.  

The script will do the following:   
- Install and configure Postgres with minimal rights
- Install and configure Nginx with maximal security
- Install and configure MrMap
- Register uwsgi, celery, celery-flower as systemd service:  
  You can restart them with systemctl restart  uwsgi, celery, celery-flower   
- Configuration files can be found in the conf folder, they are altered   
  during install if needed and placed at the following locations:  
  - /etc/nginx/conf.d/mrmap.conf -> Site conf for MrMap  
  - /opt/MrMap/MrMap/mrmap_uwsgi.ini -> uwsgi ini file  
  - /etc/systemd/system/uwsgi.service -> Systemd config for uwsgi server  
  - /etc/systemd/system/celery.service -> Systemd config for celery  
  - /etc/default/celery -> Environment file for  celery  
- Create an alias called restartMrMap to restart all MrMap related  
  services, usage: just type "restartMrMap" on command line  

At the end of the script you are asked if you would like to install ModSecurity and generate  
stronger encryption keys, this is absolutely recommended for a real production server  
facing the threats of the www, it can take up to an hour though! Can be skipped for testing and intranet only servers.  


**II.   update_mapskinner.bash**

This updates your MrMap installation.  
In the first step this will check if there are differences between your local  
and the repositories "settings.py". If there are major differences you can and  
should abort the update process to check whats missing! Adjust your local "settings.py"  
and start the update process again.  
In the next step it will backup these files:  
- MrMap/settings.py   
- service/settings.py  

Afterwards it will reset your local copy with "git reset --hard" (this will delete   
all local changes made to the code!), update it to the newest master status and puts  
configurations back to where they belong.  
In the end the script will collect all new static files and translations and  
tries to apply global migrations if there are any. Specific migrations to certain  
apps need to be done manually!   

Usage:  
```
sudo bash /opt/MrMap/install/update_mapskinner.bash
```  

**III.  mass_register.py**

Used to register a list of services at once via the mapskinner api.

The list has to contain one wms get capabilities request each line including parameters.  
Generate an API Token on the web interface and paste it into the token parameter in the script.  
Adjust the rest of the parameters in mass_register.py to your needs.

Usage:    
```
python3 /opt/MrMap/install/mass_register.py WMSLIST
```    

**IV.  Some notes on ModSecurity**

- If you get blocked while making a legitimate request, please write an issue   
or email the request to me: andre.holl@vermkv.rlp.de  
- You can disable it with:  

```
sudo sed -i 's/SecRuleEngine On/SecRuleEngine DetectionOnly/g' /etc/nginx/modsec/modsecurity.conf   
sudo /etc/init.d/nginx restart
```    
