################################
# Base build Image
################################  
FROM python:3.15.2-alpine3.24 AS compile-image
ARG MRMAP_PRODUCTION

RUN apk update && \
    apk add --no-cache build-base gdal libressl-dev

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# build python dependencies    
COPY ./.requirements /.requirements
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    /usr/local/bin/python -m pip install --upgrade pip && \
    pip install -r ./.requirements/base.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ "${MRMAP_PRODUCTION}" = "False" ] ; then pip install -r ./.requirements/dev.txt && pip install -r ./.requirements/docs.txt; fi

################################
# MrMap Image
################################    
FROM python:3.15.2-alpine3.24 AS runtime-image
ARG MRMAP_PRODUCTION
COPY --from=compile-image /opt/venv /opt/venv

# TODO: gettext are only needed for dev environment
RUN addgroup -g 1000 mrmapgroup \
    && adduser -D -u 1000 -G mrmapgroup mrmapuser \
    && apk update \
    && apk add --no-cache font-dejavu libpq netcat-openbsd yaml gettext gdal geos libressl py3-psycopg postgresql-client\
    && rm -rf /var/cache/apk/* \
    && mkdir -p /var/mrmap/backend/media \
    && mkdir -p /var/log/mrmap/backend \
    && mkdir -p /var/log/mrmap/celery-worker-default \
    && mkdir -p /var/log/mrmap/celery-worker-db-routines \
    && mkdir -p /var/log/mrmap/celery-worker-download \
    && mkdir -p /var/mrmap/import \
    && mkdir -p /var/www/mrmap/backend \ 
    && mkdir -p /var/run/celery \
    && chown -R mrmapuser:mrmapgroup \
    /opt/venv \
    /var/mrmap \
    /var/log/mrmap \
    /var/www/mrmap \
    /var/run/celery

USER mrmapuser

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/venv/bin:$PATH"


ENTRYPOINT [ "/opt/mrmap/.bash_scripts/entrypoint.sh" ]

CMD ["./.bash_scripts/startup.sh" ]

EXPOSE 8001/tcp

################################
# Versioned application artifact (#1582)
#
# The LAST stage, so every dev path - the compose services,
# .github/workflows/dev-images.yml, scripts/dev_image_id.py - must pin
# `target: runtime-image` to keep building the dependency image it always
# built; scripts/test_image_version.py fails when one forgets. The identity
# comes from the two canonical sources of #1579: the strict SemVer in the
# root VERSION file and the exact commit, passed in as build args by
# `python3 scripts/image_version.py --build-args` (the one place the rules
# live). A build that cannot name both is refused HERE, not published as
# "unknown"; tags and labels of an artifact then say the same thing, and
# `scripts/image_version.py --verify-image` reads the labels back.
################################
FROM runtime-image AS production-image

ARG MRMAP_VERSION=""
ARG MRMAP_REVISION=""
ARG MRMAP_SOURCE="https://github.com/mrmap-community/mrmap"
ARG MRMAP_CHANNEL="dev"

# The SemVer grammar of semver.org as an ERE, and the full commit SHA:
# defense in depth - the builder validates too, but the artifact must
# refuse to exist without an identity even when built by hand.
RUN set -eu; \
    semver='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9A-Za-z-]*))*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'; \
    if ! printf '%s' "$MRMAP_VERSION" | grep -Eq "$semver"; then \
        echo "REFUSED: MRMAP_VERSION='$MRMAP_VERSION' is not a strict SemVer version; build with python3 scripts/image_version.py --build-args" >&2; \
        exit 1; \
    fi; \
    if ! printf '%s' "$MRMAP_REVISION" | grep -Eq '^[0-9a-f]{40}$'; then \
        echo "REFUSED: MRMAP_REVISION='$MRMAP_REVISION' is not a full 40-hex commit SHA; the artifact names the exact commit it contains" >&2; \
        exit 1; \
    fi

# The code the dev flow only bind-mounts at this path is baked in, so the
# artifact runs without a checkout; the deployment overlay
# (deploy/docker-compose.images.yml) must then NOT re-add such a bind - it
# would shadow the artifact, the #922/#1027 stale-statics failure at the
# code root.
COPY --chown=mrmapuser:mrmapgroup . /opt/mrmap

LABEL org.opencontainers.image.title="MrMap backend" \
      org.opencontainers.image.description="MrMap geoservice registry, Django backend and Celery workers" \
      org.opencontainers.image.vendor="mrmap-community" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="$MRMAP_VERSION" \
      org.opencontainers.image.revision="$MRMAP_REVISION" \
      org.opencontainers.image.source="$MRMAP_SOURCE" \
      io.github.mrmap.channel="$MRMAP_CHANNEL"
