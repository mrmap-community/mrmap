FROM jetty:9.3.6
MAINTAINER Carlos Palma <carlospalma at guadaltel.com>
LABEL maintainer="Carlos Palma <carlospalma@guadaltel.com>"

LABEL Name="etf-webapp" Description="Testing framework for spatial data and services" Vendor="European Union, interactive instruments GmbH" Version=“2020.1”

EXPOSE 8080

ENV ETF_DIR /etf
ENV ETF_LOG_DIR /etf/logs

ENV ETF_RELATIVE_URL validator
# Possible values: “latest”, <version as MAJOR.MINOR.BUGFIX> e.g. “2.0.0” or
# <version as MAJOR.MINOR> e.g. “1.0” to get the latest bugfix version
ENV ETF_WEBAPP_VERSION latest

# Possible values: “latest”, <version as MAJOR.MINOR.BUGFIX> or
# <version as MAJOR.MINOR>
# Packed with the Webapp
ENV ETF_TESTDRIVER_BSX_VERSION latest

# Possible values: “latest”, <version as MAJOR.MINOR.BUGFIX> or
# <version as MAJOR.MINOR>
# Will be downloaded
ENV ETF_GMLGEOX_VERSION latest

# Possible values: “latest”, <version as MAJOR.MINOR.BUGFIX> or
# <version as MAJOR.MINOR>
# Packed with the Webapp
ENV ETF_TESTDRIVER_SUI_VERSION latest

# Possible values: “latest”, <version as MAJOR.MINOR.BUGFIX> or
# <version as MAJOR.MINOR>
# Packed with the Webapp
ENV ETF_TESTDRIVER_TE_VERSION latest

# Default repository configuration
ENV REPO_URL https://services.interactive-instruments.de/etfdev-af/etf-public-dev
ENV REPO_USER etf-public-dev
ENV REPO_PWD etf-public-dev

# Possible values: “none” or URL to ZIP file
ENV ETF_DL_TESTPROJECTS_ZIP https://github.com/inspire-eu-validation/ets-repository/archive/v2020.3.1.zip

# Subfolder in the projects directory
ENV ETF_DL_TESTPROJECTS_DIR_NAME inspire-ets-repository
# Possible values: true for overwriting the directory on every container start,
# false for keeping an existing directory
ENV ETF_DL_TESTPROJECTS_OVERWRITE_EXISTING true

# Maximum JAVA heap size (XmX parameter) in MB or “max” (max available memory-768MB if at least 3GB available)
ENV MAX_MEM max

# Activate HTTP proxy server by setting a host (IP or DNS name).
# Default: "none" for not using a proxy server
ENV HTTP_PROXY_HOST localhost
# HTTP proxy server port. Default 8080. If you are using Squid it is 3128
ENV HTTP_PROXY_PORT 3128
# Optional username for authenticating against HTTP proxy server or "none" to
# deactivate authentication
ENV HTTP_PROXY_USERNAME none
# Optional password for authenticating against HTTP proxy server or "none"
ENV HTTP_PROXY_PASSWORD none

# Activate HTTP Secure proxy server by setting a host (IP or DNS name).
# Default: "none" for not using a proxy server
ENV HTTPS_PROXY_HOST none
# HTTP Secure proxy server port. Default 3129.
ENV HTTPS_PROXY_PORT 3129
# Optional username for authenticating against HTTPS proxy server or "none" to
# deactivate authentication
ENV HTTPS_PROXY_USERNAME none
# Optional password for authenticating against HTTP Secure proxy server or "none"
ENV HTTPS_PROXY_PASSWORD none

RUN mv /docker-entrypoint.bash /docker-entrypoint-jetty.bash
COPY res/docker-entrypoint.sh /

RUN apt-get update; true
RUN apt-get install -y squid3 zip unzip
COPY res/squid.conf /etc/squid3/squid.conf


RUN apt-get install -y apache2
COPY res/proxy.conf /etc/apache2/sites-available/proxy.conf

RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partaa?raw=true -O validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partab?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partac?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partad?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partae?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partaf?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partag?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partah?raw=true -O ->> validator_war.zip
RUN wget https://github.com/mrmap-community/artefacts/blob/8d427ee00ab046beb2e0ea5100331f19746d4958/validator_war.zip.partai?raw=true -O ->> validator_war.zip

# RUN cat validator_war.zip.parta* > validator_war.zip
RUN zip -F validator_war.zip --out validator.war
RUN rm validator_war*
RUN mv $ETF_RELATIVE_URL.war /var/lib/jetty/webapps
RUN chown jetty:jetty /var/lib/jetty/webapps

#COPY --chown=jetty:jetty $ETF_RELATIVE_URL.war /var/lib/jetty/webapps
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["java","-jar","/usr/local/jetty/start.jar"]
