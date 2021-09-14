# debian 11 image
FROM python:3.9.7-bullseye as base
# todo check if all this packages are still needed...
RUN apt-get -qq update && \
    apt-get -y install gcc
COPY requirements.txt /
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

FROM python:3.9.7-slim-bullseye
ARG ENV
RUN apt-get -qq update && \
    apt-get -y install libssl-dev gdal-bin libpq-dev netcat

COPY --from=base /wheels /wheels
COPY --from=base requirements.txt .
RUN pip install --no-cache /wheels/* # flask, gunicorn, pycrypto

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# run entrypoint.sh
ENTRYPOINT ["/opt/mrmap/entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]