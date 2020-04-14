# install(script) nginx + uwsgi + django + mapskinner/mrmap:
#!/bin/bash
mrmap_db_user=mrmap_db_user
mrmap_db_pw=mrmap_db_pw
hostname=127.0.0.1

# install required packages
apt-get install -y postgresql postgresql-client postgis redis-server libcurl4-openssl-dev libssl-dev virtualenv build-essential git python3-pip fcgiwrap cgi-mapserver apache2-utils curl gnupg2 ca-certificates lsb-release gettext

# add nginx official mainline repo
echo "deb http://nginx.org/packages/mainline/debian `lsb_release -cs` nginx" \
    | tee /etc/apt/sources.list.d/nginx.list
curl -fsSL https://nginx.org/keys/nginx_signing.key | apt-key add -
apt-key fingerprint ABF5BD827BD9BF62
apt-get update
apt-get install nginx

# make python3 default
update-alternatives --install /usr/bin/python python /usr/bin/python3.7 1

#db setup
su - postgres -c "psql -c \"CREATE USER $mrmap_db_user WITH ENCRYPTED PASSWORD '$mrmap_db_pw';\""
su - postgres -c "psql -c 'CREATE DATABASE \"MrMap\" OWNER $mrmap_db_user;'"

# temporarily set postgres to trust, needed to create postgis
sed -i s/"host    all             all             127.0.0.1\/32            md5"/"host    all             all             127.0.0.1\/32            trust"/g /etc/postgresql/11/main/pg_hba.conf

/etc/init.d/postgresql restart

# mapskinner setup, has to be done as postgres because of postgis extension

git clone https://git.osgeo.org/gitea/GDI-RP/MapSkinner /opt/MapSkinner
python -m pip install uwsgi flower
python -m pip install -r /opt/MapSkinner/requirements.txt
python /opt/MapSkinner/manage.py makemigrations service
python /opt/MapSkinner/manage.py makemigrations structure
python /opt/MapSkinner/manage.py migrate
python /opt/MapSkinner/manage.py collectstatic

# changes to settings.py, set Django debug to false, set hostname
sed -i s/"DEBUG = True"/"DEBUG = False"/g /opt/MapSkinner/MapSkinner/settings.py
sed -i s/"HOST_NAME = \"127.0.0.1:8000\""/"HOST_NAME = \"$hostname\""/g /opt/MapSkinner/MapSkinner/settings.py

# remove postgres trust, replace with mr map database user
sed -i s/"host    all             all             127.0.0.1\/32            trust"/"host    MrMap             $mrmap_db_user             127.0.0.1\/32            md5"/g /etc/postgresql/11/main/pg_hba.conf

/etc/init.d/postgresql restart


# change settings.py to dedicated user
sed -i s/"        'USER': 'postgres',"/"        'USER': '$mrmap_db_user',"/g /opt/MapSkinner/MapSkinner/settings.py

if  ! grep -q "        'PASSWORD': '$mrmap_db_pw',"  /opt/MapSkinner/MapSkinner/settings.py ;then
	sed -i "/        'USER': '$mrmap_db_user',/a \        \'PASSWORD': '$mrmap_db_pw'," /opt/MapSkinner/MapSkinner/settings.py
fi

# db setup done

# create ssl cert, self signed for now
echo "                     !!! ATTENTION !!!

creating a self signed cert, just smash enter and change the cert to a valid one afterwards
public:  /etc/ssl/certs/nginx-selfsigned.crt
private: /etc/ssl/private/nginx-selfsigned.key

                     !!! ATTENTION !!!"
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt

echo "Generating Secure Diffie-Hellman for TLS, this may take a while"
#generate new one with 4096 bits for real production
openssl dhparam -out /etc/ssl/certs/dhparams.pem 2048

# get nginx config, later this will be: cp -a /opt/MapSkinner/install/confs/mrmap_nginx /etc/nginx/sites-available/mrmap
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_nginx -O /etc/nginx/conf.d/mrmap.conf
# replace hostname in nginx config
sed -i s/"    server_name 127.0.0.1;"/"    server_name $hostname;"/g /etc/nginx/conf.d/mrmap.conf
sed -i s/"    server_name         127.0.0.1;"/"    server_name         $hostname;"/g /etc/nginx/conf.d/mrmap.conf

# disable server tokens
sed -i "/http {/a \    \server_tokens off;" /etc/nginx/nginx.conf

rm /etc/nginx/conf.d/default.conf


# get uwsgi ini, later this will be: cp -a /opt/MapSkinner/install/confs/mrmap_uwsgi_ini /opt/MapSkinner/MapSkinner/mrmap_uwsgi.ini
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_uwsgi_ini -O /opt/MapSkinner/MapSkinner/mrmap_uwsgi.ini


# get script to change db rights, later:  cp -a /opt/MapSkinner/install/confs/change_db_rights /tmp/change_database_rights.psql
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/change_db_rights -O /tmp/change_database_rights.psql
sed -i s/\$mrmap_db_user/$mrmap_db_user/g /tmp/change_database_rights.psql
# execute
su - postgres -c "psql -d 'MrMap' -f /tmp/change_database_rights.psql"


# get uwsgi systemd config, later: cp -a /opt/MapSkinner/install/confs/mrmap_uwsgi_service /etc/systemd/system/uwsgi.service
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_uwsgi_service -O /etc/systemd/system/uwsgi.service

# start uwsgi and enable start on boot
systemctl start uwsgi
#systemctl stop uwsgi
#systemctl restart uwsgi
#systemctl status celery
systemctl enable uwsgi

# celery

mkdir /var/log/celery/
mkdir /var/run/celery/
chown www-data:www-data /var/log/celery/
chown www-data:www-data /var/run/celery/


# get celery environment file, later: cp -a /opt/MapSkinner/install/confs/mrmap_celery_environment /etc/default/celery
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_celery_environment -O /etc/default/celery

# get celery service file, later: cp -a /opt/MapSkinner/install/confs/mrmap_celery_service /etc/systemd/system/celery.service
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_celery_service -O /etc/systemd/system/celery.service

# start celery and enable start on boot
systemctl start celery
#systemctl stop celery
#systemctl restart celery
#systemctl status celery
systemctl enable celery


# get celery helper service file, later: cp -a /opt/MapSkinner/install/confs/mrmap_celery_helper_service /etc/systemd/system/celery-helper.service
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_celery_helper_service -O /etc/systemd/system/celery-helper.service
systemctl enable celery-helper

# get celery flower statistics service file, later: cp -a /opt/MapSkinner/install/confs/mrmap_celery_helper_service /etc/systemd/system/celery-helper.service
wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/confs/mrmap_celery_flower_service -O /etc/systemd/system/celery-flower.service
systemctl enable celery-flower
systemctl start celery-flower


systemctl daemon-reload

echo "Enter password for basic auth for celery statistics, available under /flower, username is root for now"
htpasswd -c /etc/nginx/.htpasswd root


wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/214_Production_setup/install/modsecurity_and_stronger_DH.bash -O /opt/modsecurity_and_stronger_DH.bash

while true; do
    read -p "Do you want to install Modsecurity and generate stronger Key Exchange Algorithm? This can take up to 30mins, recommended for production!y/n? \
You can do this later with bash /opt/MapSkinner/install/modsecurity_and_stronger_DH.bash " yn
    case $yn in
        [Yy]* )
				# later : bash /opt/MapSkinner/install/modsecurity_and_stronger_DH.bash;
				bash /opt/modsecurity_and_stronger_DH.bash;
        break;;
        [Nn]* ) break;;
        * ) echo "Please answer yes or no.";;
    esac
done

echo '
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMNmhyyyyhhhddmMMMMMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMNmhso/:.`./`.oshdddhs++symMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMNmdyo+:-:/-.``````.sdmdhysoosmh++++oyNMMMMMM
MMMMMMMMMMMMMMMMMMMNddyso++/```````````-....sNo++++++++oMo+++++oyMMMMM
MMMMMMMMMMMMMMMmy+::++++++++.````````:+o++++dd+++++++++yNo+++++++oNMMM
MMMMMMMMMMMMNho+++++++++++++.`.-/+sydNMMo+++sNyooosyhdmNs+++++++-.:mMM
MMMMMMMMMMms+++::+++++++++ommNMMMNmddhy/+++++ohmmddhyhshyo+++++++.`:MM
MMMMMMMMMo//++/``.``-+++++/yss+-.```://:+++++++:++++++syyyhso+++/.``sM
MMMMMMMm/:::://:--.``-+++-```````./-.+++ooo:+hmmddho++++syyos++-``-..M
MMMMMMN+--:/:/+/:/+/``.:/.```````--/+odNMMMNMMMMMMMMdo++++::/+++``.-.d
MMMMMMy/++-:+++/.:/:.``````````````-yMMMMMMMMMMMMMMMMNs/+:```.oo`-+-.y
MMMMMdos++++++..`/+++/:.```````````yMMMMMMMMMMMMMMMMMMMd+:.``.sM/-:.-s
MMMMMhyyo+++++---.++++-:.`````````-MMMMMMMMMddMMMMMMMMMMMds+ohMM:..``y
MMMMMyyys++++++++++++/-```````````dMMMMMMMMNo+ymMMMMMMMMMMMMMMm/````-d
MMMMMyyyyo++++++++++/`````+-`````oMMMMMMMMNo++++shdNMMMMMMNho:``````+M
MMMMMs+syyo+++++++++:`````Nh.``:yMMMMMMMMh++++++++.`.---.```` `````.NM
MMMMMy//+yyo+++++++/``````+MMMMMMMMMMMms.`./+++++++`/-````    ````.dMM
MMMMMN///+yys+++/.``--..```-ohdmmdhs/-``````-+++++:`/-`  `:so ```-mMMM
MMMMMMs/////oo+++.-:.``--::--````          `.///++:`  `:oyyyy` `sMMMMM
MMMMMMN+////////:---:.-++++++++++- +soo+//::--..``  -oyyyyyyy- mMMMMMM
MMMMMMMN+///////:-````.++++++++++- :yyyyyyyyyyyyyyyyyyyyyyyyy+ sMMMMMM
MMMMMMMMNo/////////:.``/+++++++++: `yyyyyyyyyyyyyyyyyyyyyyyyyy -MMMMMM
MMMMMMMMMMd+//////////:--//+++++-`  oyyyyyyyyyyyyy+-........--` mMMMMM
MMMMMMMMMMMMds/////////////yysss:-- :yyyyyyyyyy+- .odddddddhhhhhmMMMMM
MMMNNmMMNmo/:sMmhso++/////+yhhddhdN-`yyyyyyy+. -omMMMMMMMMMMMMMMMMMMMM
Ndy...+mhs.-.:NMdmNhydMMMMMMMMMMMMMo oyys/. -smMMMMMMMMMMMMMMMMMMMMMMM
mhh:.+./yo.o-.hh::-:+yMMMMMMMMMMMMMm -/. :yNMMMMMMMMMMMMMMMMMMMMMMMMMM
Mhh+.os-::.y/.ohs.-dmMMMMMMMMMMMMMMM.`:yNMMMMNds+/::+hmMMMMMMMMMMMMMMM
Mdhy./hy/./hs.:hyo.mMMMMNddMMMMMMNmMmNMMMMMmh-..osss+--sNMMMMMMMMMMMMM
Mmhh--dhhydhh-.yhy/odmMmy//mMNdo/--+mMMMMMdhh+..hdhhhs..hMMMMMMMMMMMMM
MNhh+-hNmmNhhsshs/:..+NNmNMNhhs..+..:dMMMMmhhy..+MNhy/.:mMMMMMMMMMMMMM
MMdhhy/-:.-smhhh/....-hMMMMmhy+..yy:.-sNMMMhhh+..ss/-./yNMMMMMMMMMMMMM
MMmhhh-..-..ydhy:.-/..oMMMMdhh:.-hhy/..+NMMdhhy...:+oymMMMMMMMMMMMMMMM
MMNhhho..+/..ohh-.+s../NMMNhhy-./ho/-...:dMmhhy:.-ydNMMMMMMMMMMMMMMMMM
MMMdhhy..:ho-./s..sh-.-dMMdhho....-/oyy:.-omhhh+../NMMMMMMMMMMMMMMMMMM
MMMmhhh/.-hhs-...-hh+..sNMhhh/..:yhdhhhh/../hhhy..-dMMMMMMMMMMMMMMMMMM
MMMMhhho..shyy+../hhy..-mmhhy...+mMMNdhhyo-:dhhy+osdMMMMMMMMMMMMMMMMMM
MMMMdhhy..+dhhhsyhhhh:..shhho---hMMMMMmhhhhNMhhhhhmMMMMMMMMMMMMMMMMMMM
MMMMmhhh/.-dNhhdmMhhh+--ohhhhhyhNMMMMMMNNMMMMMNMMMMMMMMMMMMMMMMMMMMMMM
MMMMNhhho--yMMMMMMmhhhhhmmmdddmMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMdhhhhhhMMMMMMNmdmmNMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMNhhddmMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM

'
echo "Congratulations, MapSkinner is installed on your system!"
echo "Please execute \"python /opt/MapSkinner/manage.py setup\" to create a user, afterwards access with browser and have fun :)"

/etc/init.d/nginx restart
systemctl restart uwsgi
