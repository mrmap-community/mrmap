#!/bin/bash
openssl dhparam -out /etc/ssl/certs/dhparams.pem 4096
apt-get install -y apt-utils autoconf automake build-essential git libcurl4-openssl-dev libgeoip-dev liblmdb-dev libpcre++-dev libtool libxml2-dev libyajl-dev pkgconf wget zlib1g-dev
cd /opt/
git clone --depth 1 -b v3/master --single-branch https://github.com/SpiderLabs/ModSecurity
cd ModSecurity
git submodule init
git submodule update
./build.sh
./configure
make
make install
git clone --depth 1 https://github.com/SpiderLabs/ModSecurity-nginx.git
nginx -v > /tmp/nginx.version 2>&1
nginx_version=`cat /tmp/nginx.version | cut -d "/" -f 2`
wget "http://nginx.org/download/nginx-$nginx_version.tar.gz"
tar zxvf nginx-$nginx_version.tar.gz
cd nginx-$nginx_version
#export MODSECURITY_INC="/opt/ModSecurity/headers/"
#export MODSECURITY_LIB="/opt/ModSecurity/src/.libs/"
nginx -V > /tmp/nginx.options_tmp 2>&1
tail -1 /tmp/nginx.options_tmp >> /tmp/nginx.compile_options
nginx_compile_options=`awk -F'--with-debug' '{print $1}' /tmp/nginx.compile_options | cut -d ":" -f 2`
./configure --with-compat --add-dynamic-module=../ModSecurity-nginx #`echo $nginx_compile_options`
make modules
cp objs/ngx_http_modsecurity_module.so /etc/nginx/modules
echo 'load_module modules/ngx_http_modsecurity_module.so;' > /tmp/temp_file
cat /etc/nginx/nginx.conf >> /tmp/temp_file
mv /tmp/temp_file /etc/nginx/nginx.conf
mkdir /etc/nginx/modsec
wget -P /etc/nginx/modsec/ https://raw.githubusercontent.com/SpiderLabs/ModSecurity/v3/master/modsecurity.conf-recommended
mv /etc/nginx/modsec/modsecurity.conf-recommended /etc/nginx/modsec/modsecurity.conf
sed -i s/"SecUnicodeMapFile unicode.mapping 20127"/"#SecUnicodeMapFile unicode.mapping 20127"/g /etc/nginx/modsec/modsecurity.conf
sed -i "/add_header X-XSS-Protection \"1; mode=block\";/a \    \modsecurity on;" /etc/nginx/conf.d/mrmap.conf
sed -i "/modsecurity on;/a \    \modsecurity_rules_file /etc/nginx/modsec/main.conf;" /etc/nginx/conf.d/mrmap.conf
