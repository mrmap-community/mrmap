# install(script) nginx + uwsgi + django + MrMap:
#!/bin/bash
mrmap_db_user=mrmap_db_user
mrmap_db_pw=mrmap_db_pw
hostname=127.0.0.1
proxy="" # format: proxy = "192.168.56.1:8080"

# install required packages
apt-get update
apt-get install -y postgresql postgresql-client postgresql-server-dev-11 postgis redis-server libcurl4-openssl-dev libssl-dev virtualenv build-essential git python3-pip fcgiwrap cgi-mapserver apache2-utils curl gnupg2 ca-certificates lsb-release gettext

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

# MrMap setup, has to be done as postgres because of postgis extension

git clone https://git.osgeo.org/gitea/GDI-RP/MrMap /opt/MrMap
python -m pip install --upgrade pip
python -m pip install uwsgi flower
python -m pip install -r /opt/MrMap/requirements.txt --use-feature=2020-resolver
python /opt/MrMap/manage.py makemigrations service
python /opt/MrMap/manage.py makemigrations structure
python /opt/MrMap/manage.py makemigrations users
python /opt/MrMap/manage.py makemigrations monitoring
python /opt/MrMap/manage.py makemigrations editor
python /opt/MrMap/manage.py migrate
python /opt/MrMap/manage.py collectstatic

# changes to settings.py, set Django debug to false, set hostname, enable ssl
sed -i s/"DEBUG = True"/"DEBUG = False"/g /opt/MrMap/MrMap/sub_settings/django_settings.py
sed -i s/"HOST_NAME = \"127.0.0.1:8000\""/"HOST_NAME = \"$hostname\""/g /opt/MrMap/MrMap/sub_settings/dev_settings.py
sed -i s/"HTTP_OR_SSL = \"http:\/\/\""/"HTTP_OR_SSL = \"https:\/\/\""/g /opt/MrMap/MrMap/sub_settings/dev_settings.py
sed -i s/"HTTP_PROXY = \"\""/"HTTP_PROXY = \"http:\/\/$proxy\""/g /opt/MrMap/MrMap/settings.py
# generate new secret key
skey=`python /opt/MrMap/manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
sed -i '/^SECRET_KEY/d' /opt/MrMap/MrMap/sub_settings/django_settings.py
sed -i "/# SECURITY WARNING: keep the secret key used in production secret\!/a SECRET_KEY = '$skey'" /opt/MrMap/MrMap/sub_settings/django_settings.py
# remove postgres trust, replace with mr map database user
sed -i s/"host    all             all             127.0.0.1\/32            trust"/"host    MrMap             $mrmap_db_user             127.0.0.1\/32            md5"/g /etc/postgresql/11/main/pg_hba.conf

/etc/init.d/postgresql restart


# change settings.py to dedicated user
sed -i s/"        'USER': 'postgres',"/"        'USER': '$mrmap_db_user',"/g /opt/MrMap/MrMap/sub_settings/db_settings.py

if  ! grep -q "        'PASSWORD': '$mrmap_db_pw',"  /opt/MrMap/MrMap/sub_settings/db_settings.py ;then
	sed -i "/        'USER': '$mrmap_db_user',/a \        \'PASSWORD': '$mrmap_db_pw'," /opt/MrMap/MrMap/sub_settings/db_settings.py
fi

# db setup done

# create ssl cert, self signed for now
echo "                     !!! ATTENTION !!!

creating a self signed cert, just smash enter and change the cert to a valid one afterwards
public:  /etc/ssl/certs/nginx-selfsigned.crt
private: /etc/ssl/private/nginx-selfsigned.key

                     !!! ATTENTION !!!"
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt

echo "Generating Secure Diffie-Hellman for TLS it not already there, this may take a while"
#generate new one with 4096 bits for real production
if [ ! -f /etc/ssl/certs/dhparams.pem ]; then
    openssl dhparam -out /etc/ssl/certs/dhparams.pem 2048
fi

# copy nginx config
cp -a /opt/MrMap/install/confs/mrmap_nginx /etc/nginx/conf.d/mrmap.conf
# replace hostname in nginx config
sed -i s/"    server_name 127.0.0.1;"/"    server_name $hostname;"/g /etc/nginx/conf.d/mrmap.conf
sed -i s/"    server_name         127.0.0.1;"/"    server_name         $hostname;"/g /etc/nginx/conf.d/mrmap.conf

# disable server tokens, it not done already
if  ! grep -q "server_tokens off;"  /etc/nginx/nginx.conf ;then
  sed -i "/http {/a \    \server_tokens off;" /etc/nginx/nginx.conf
fi
rm /etc/nginx/conf.d/default.conf

# copy uwsgi ini
cp -a /opt/MrMap/install/confs/mrmap_uwsgi_ini /opt/MrMap/MrMap/mrmap_uwsgi.ini

# copy script to change database rights
cp -a /opt/MrMap/install/confs/change_db_rights /tmp/change_database_rights.psql

sed -i s/\$mrmap_db_user/$mrmap_db_user/g /tmp/change_database_rights.psql
# execute
su - postgres -c "psql -d 'MrMap' -f /tmp/change_database_rights.psql"


# copy uwsgi systemd config
cp -a /opt/MrMap/install/confs/mrmap_uwsgi_service /etc/systemd/system/uwsgi.service

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


# copy celery environment file
cp -a /opt/MrMap/install/confs/mrmap_celery_environment /etc/default/celery

# copy celery service file
cp -a /opt/MrMap/install/confs/mrmap_celery_service /etc/systemd/system/celery.service

# start celery and enable start on boot
systemctl start celery
systemctl enable celery


# copy celery helper service file
cp -a /opt/MrMap/install/confs/mrmap_celery_helper_service /etc/systemd/system/celery-helper.service
systemctl enable celery-helper

# copy celery flower statistics service file
cp -a /opt/MrMap/install/confs/mrmap_celery_flower_service /etc/systemd/system/celery-flower.service
systemctl enable celery-flower
systemctl start celery-flower


systemctl daemon-reload

if  ! grep -q "restartMrMap"  /etc/bash.bashrc ;then
echo "alias "restartMrMap"=\"systemctl restart celery;systemctl restart uwsgi;systemctl restart celery-flower;/etc/init.d/nginx restart\"" >> /etc/bash.bashrc
fi

echo "Enter password for basic auth for celery statistics, available under /flower, username is root for now"
htpasswd -c /etc/nginx/.htpasswd root


while true; do
    read -p "Do you want to install Modsecurity and generate stronger Key Exchange Algorithm? \n
This can take up to 1 hour, recommended for production!y/n? \n
You can do this later with bash /opt/MrMap/install/modsecurity_and_stronger_DH.bash " yn
    case $yn in
        [Yy]* )
				bash /opt/MrMap/install/modsecurity_and_stronger_DH.bash;
        break;;
        [Nn]* ) break;;
        * ) echo "Please answer yes or no.";;
    esac
done
echo "Executing initial setup"
python /opt/MrMap/manage.py setup
chown -R www-data /opt/MrMap/logs

/etc/init.d/nginx restart
systemctl restart uwsgi

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
echo "Congratulations, MrMap is installed on your system!"
