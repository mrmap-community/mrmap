#!/bin/bash
# this script adds an additional layer of security to you mrmap installation.
# to achieve this it generates stronger encryption keys and configures modsecurity
# with the OWASP core rule set. https://github.com/SpiderLabs/owasp-modsecurity-crs
# This can take up to an hour!

#generate stonger Diffie Hellman Key
openssl dhparam -out /etc/ssl/certs/dhparams.pem 4096
# requirements for modsecruity
apt-get install -y apt-utils autoconf automake build-essential git libcurl4-openssl-dev libgeoip-dev liblmdb-dev libpcre++-dev libtool libxml2-dev libyajl-dev pkgconf wget zlib1g-dev
# modsecurity setup
cd /opt/
git clone --depth 1 -b v3/master --single-branch https://github.com/SpiderLabs/ModSecurity
cd ModSecurity
git submodule init
git submodule update
./build.sh
./configure
make
make install
# compile nginx, this is only needed to create the modsecurity module,
# Nginx will still be installed from packages
git clone --depth 1 https://github.com/SpiderLabs/ModSecurity-nginx.git
nginx -v > /tmp/nginx.version 2>&1
nginx_version=`cat /tmp/nginx.version | cut -d "/" -f 2`
wget "http://nginx.org/download/nginx-$nginx_version.tar.gz"
tar zxvf nginx-$nginx_version.tar.gz
cd nginx-$nginx_version
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
sed -i "/\    \modsecurity on;/a \    \modsecurity_rules_file /etc/nginx/modsec/modsec_includes.conf;" /etc/nginx/conf.d/mrmap.conf
cd /etc/nginx/
git clone https://github.com/SpiderLabs/owasp-modsecurity-crs.git
cd owasp-modsecurity-crs
cp -a crs-setup.conf.example crs-setup.conf
cp -a rules/REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf.example rules/REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf
cp -a rules/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf.example rules/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf
sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' /etc/nginx/modsec/modsecurity.conf
cat << EOF > /etc/nginx/modsec/rule-exclusions.conf
# exclude uris for rfi attacks, needed for service registration
SecRuleUpdateTargetById 931120 "!ARGS:uri"
EOF

cat << EOF > /etc/nginx/modsec/modsec_includes.conf
include ../modsec/modsecurity.conf
include ../modsec/rule-exclusions.conf
include ../owasp-modsecurity-crs/crs-setup.conf
include ../owasp-modsecurity-crs/rules/REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf
include ../owasp-modsecurity-crs/rules/REQUEST-901-INITIALIZATION.conf
include ../owasp-modsecurity-crs/rules/REQUEST-905-COMMON-EXCEPTIONS.conf
include ../owasp-modsecurity-crs/rules/REQUEST-910-IP-REPUTATION.conf
include ../owasp-modsecurity-crs/rules/REQUEST-911-METHOD-ENFORCEMENT.conf
include ../owasp-modsecurity-crs/rules/REQUEST-912-DOS-PROTECTION.conf
include ../owasp-modsecurity-crs/rules/REQUEST-913-SCANNER-DETECTION.conf
include ../owasp-modsecurity-crs/rules/REQUEST-920-PROTOCOL-ENFORCEMENT.conf
include ../owasp-modsecurity-crs/rules/REQUEST-921-PROTOCOL-ATTACK.conf
include ../owasp-modsecurity-crs/rules/REQUEST-930-APPLICATION-ATTACK-LFI.conf
include ../owasp-modsecurity-crs/rules/REQUEST-931-APPLICATION-ATTACK-RFI.conf
include ../owasp-modsecurity-crs/rules/REQUEST-932-APPLICATION-ATTACK-RCE.conf
include ../owasp-modsecurity-crs/rules/REQUEST-933-APPLICATION-ATTACK-PHP.conf
include ../owasp-modsecurity-crs/rules/REQUEST-941-APPLICATION-ATTACK-XSS.conf
include ../owasp-modsecurity-crs/rules/REQUEST-942-APPLICATION-ATTACK-SQLI.conf
include ../owasp-modsecurity-crs/rules/REQUEST-943-APPLICATION-ATTACK-SESSION-FIXATION.conf
include ../owasp-modsecurity-crs/rules/REQUEST-949-BLOCKING-EVALUATION.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-950-DATA-LEAKAGES.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-951-DATA-LEAKAGES-SQL.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-952-DATA-LEAKAGES-JAVA.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-953-DATA-LEAKAGES-PHP.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-954-DATA-LEAKAGES-IIS.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-959-BLOCKING-EVALUATION.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-980-CORRELATION.conf
include ../owasp-modsecurity-crs/rules/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf
EOF
