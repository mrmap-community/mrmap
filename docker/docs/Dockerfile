# Documentation build image (#1597, epic #1589).
#
# An *isolated* environment in the literal sense: this image carries the pinned
# toolchain from backend/.requirements/docs.txt and nothing else - no Django, no
# GDAL, no database client. docs/source/conf.py is written so that the portal
# builds without the application importable, which is what lets this image stay
# small and lets a contributor build the same artifact with a venv plus the same
# one requirements file. The previous image installed gcc, libssl-dev, gdal-bin
# and the whole backend requirement set (from a ./mrmap/ path the backend move
# removed, so it no longer even built), and apt's own python3-sphinx on top -
# three version sources for one toolchain, none of them pinned.
#
# git is the one non-Python package: sphinx-multiversion, which the entrypoint
# runs to document the released tags, reads the repository's refs.
FROM python:3.13-slim-bookworm

RUN apt-get -qq update \
    && apt-get -y install --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY backend/.requirements/docs.txt /tmp/docs.txt
RUN /usr/local/bin/python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/docs.txt \
    && rm /tmp/docs.txt

WORKDIR /opt/mrmap

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENTRYPOINT [ "/opt/mrmap/docker/docs/entrypoint.sh" ]
