.. _installation-6-http-server:

========
6. Nginx
========

## Install

For hosting our web application we will use [the most
popular web server on the internet](https://news.netcraft.com/archives/category/web-server-survey/)
: the [Nginx](https://nginx.org) webserver.

### Debian

```no-highlight
apt install -y nginx fcgiwrap
```

## Configure

We confiure our webserver to serve SSL traffic, if you dont want to encrypt your data there
is another configuration file for plain HTTP in the conf folder.

1. Create a certificate:

```no-highlight
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt
```

1. Copy Nginx config file to its place and enable it by creating a symlink. Delete the default conf.

!!! Note
    If youre not installing to /opt/ you have to change the folder of the /static route in the [nginx conf](https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_nginx_ssl).
    

```no-highlight
cp -a /opt/mrmap/install/confs/mrmap_nginx_ssl /etc/nginx/sites-available/mrmap
rm /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/mrmap /etc/nginx/sites-enabled/mrmap
```

1. Change server_name to your name or ipaddress in /etc/nginx/sites-available/mrmap
```no-highlight
change server_name in /etc/nginx/sites-available/mrmap
```

1. Change HTTP_OR_SSL setting in dev_settings.py
```no-highlight
change HTTP_OR_SSL to "https://" in /opt/mrmap/mrmap/MrMap/sub_settings/dev_settings.py
```

## Verify Service Status

1. Restart webserver and test

```no-highlight
systemctl restart nginx
```

1. You should see the login page after opening http://YOUR-IP-ADDRESS:

    ![login page](../installation/mrmap_loginpage.png)
