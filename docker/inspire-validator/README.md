# etf-WebApp docker image
Docker image of the ETF web application, in the INSPIRE validation version.
ETF is an open source testing framework for testing geospatial services and datasets.
The image is based on the official jetty image.

For any issue related to the deployment and operation of the INSPIRE validator [here](https://github.com/inspire-eu-validation/community/issues).

## Prerequesites

This docker image requires an [installed and configured the docker-engine](https://docs.docker.com/engine/installation/). This image has been tested on
Linux machines. Please see the [ETF documentation](https://docs.etf-validator.net/v2.0/Admin_manuals/index.html) for alternative installation options.

## Quickstart
To start a new container on port 8080 and create a 'etf' data directory in your
home directory, run the following command:

```CMD
docker run --name etf -d -p 80:8080 -v ~/etf:/etf iide/etf-webapp:latest
```

If you need to change the host data directory,
you must change the first value after the '-v' parameter, for instance
`-v /home/user1/my_etf:etf`.
See the [Docker  documentation](https://docs.docker.com/engine/reference/commandline/run/)
for more information.

Open your browser and enter the URL (http://localhost/etf-webapp) which should
show the web interface (note that the startup may need some time).

If you want to run the webapp in another host, you can change the configuration file, inside the .war file, at ```WEB-INF/classes/etf-config.properties```, and modify the `etf.webapp.base.url` property.

## Log file
The log file etf.log is located in the _/etf/logs_ directory.

## Organization internal proxy server
If outgoing network traffic is filtered by a proxy server in your organization,
you need to configure the container with proxy settings before startup.
The .war file provides settings for configuring proxy server for HTTP and
HTTP Secure, in the same sense to the base URL mentioned before:

```CMD
# Activate HTTP proxy server by setting a host (IP or DNS name).
# Default: "none" for not using a proxy server. For the built image, the proxy host is set to "localhost"
HTTP_PROXY_HOST none
# HTTP proxy server port. Default 8080. If you are using Squid it is 3128.
For the built image, the proxy port is set to 3128
HTTP_PROXY_PORT 8080
# Optional username for authenticating against HTTP proxy server or "none" to
# deactivate authentication
HTTP_PROXY_USERNAME none
# Optional password for authenticating against HTTP proxy server or "none"
HTTP_PROXY_PASSWORD none

# Activate HTTP Secure proxy server by setting a host (IP or DNS name).
# Default: "none" for not using a proxy server
HTTPS_PROXY_HOST none
# HTTP Secure proxy server port. Default 3129.
HTTPS_PROXY_PORT 3129
# Optional username for authenticating against HTTPS proxy server or "none" to
# deactivate authentication
HTTPS_PROXY_USERNAME none
# Optional password for authenticating against HTTP Secure proxy server or "none"
HTTPS_PROXY_PASSWORD none
```

## Update Executable Test Suites
To update the Executable Test Suites, you can copy the new Executable Test Suites
into the _/etf/projects/_ directory (or the subdirectories). The instance will
automatically reload the Executable Test Suites after some time.

## Custom Executable Test Suites
If you want to deploy your instance directly with custom Executable Test Suites
that are downloaded on container startup, you can change the Dockerfile environment variable REPO_URL to your own downloable resources, in .zip format.
