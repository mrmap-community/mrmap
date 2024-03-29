################################
# Base build Image
################################  
FROM python:3.10.4-bullseye AS compile-image
ARG MRMAP_PRODUCTION
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# build python dependencies    
COPY ./mrmap/requirements.txt /
COPY ./mrmap/.requirements /.requirements

RUN /usr/local/bin/python -m pip install --upgrade pip && \
    pip install -r requirements.txt

################################
# MrMap Image
################################    
FROM python:3.10.4-slim-bullseye as runtime-image
ARG MRMAP_PRODUCTION
COPY --from=compile-image /opt/venv /opt/venv

# TODO: gettext are only needed for dev environment
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends git libssl-dev gdal-bin libpq-dev netcat libyaml-dev gettext python3-sphinx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# set work directory
WORKDIR /opt/mrmap/

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT [ "/opt/mrmap/docker/docs/entrypoint.sh" ]