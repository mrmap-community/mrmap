.. _installation-1-postgresql:

=============
1. PostgreSQL
=============

This section entails the installation and configuration of a local PostgreSQL database.

!!! warning
    Please note that MySQL and other relational databases are currently **not** supported.

Installation
************

**Debian**

Install the PostgreSQL server and client development libraries using `apt`.

```no-highlight
apt update
apt install -y postgresql postgresql-client postgis* postgresql-server-dev-11
```

Database Creation
*****************

At a minimum, we need to create a database for MrMap and assign it a username and password for authentication. This is done with the following commands.
We also add the postgis extension at this stage as this has to be done by the root user.

!!! danger
    **Do not use the password from the example.** Choose a strong, random password to ensure secure database authentication for your MrMap installation.

.. code-block::
   $ su postgres
   $ psql
   psql (11.10 (Debian 11.10-0+deb10u1))
   Type "help" for help.


postgres=# CREATE DATABASE mrmap;
CREATE DATABASE
postgres=# CREATE USER mrmap WITH PASSWORD 'J5brHrAXFLQSif0K';
CREATE ROLE
postgres=# GRANT ALL PRIVILEGES ON DATABASE mrmap TO mrmap;
GRANT
postgres=# \c mrmap;
You are now connected to database "mrmap" as user "postgres".
postgres=# CREATE EXTENSION postgis;
CREATE EXTENSION
postgres=# \q
```

Verify Service Status
*********************

You can verify that authentication works issuing the following command and providing the configured password. (Replace `localhost` with your database server if using a remote database.)

```no-highlight
$ psql --username mrmap --password --host localhost mrmap
Password for user mrmap:
psql (11.10 (Debian 11.10-0+deb10u1))
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, bits: 256, compression: off)
Type "help" for help.

mrmap=> \conninfo
You are connected to database "mrmap" as user "mrmap" on host "localhost" (address "127.0.0.1") at port "5432".
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, bits: 256, compression: off)
mrmap=> \q
```

If successful, you will enter a `mrmap` prompt. Type `\conninfo` to confirm your connection, or type `\q` to exit.
