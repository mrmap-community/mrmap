# debian 11 image
# todo: check if alpine image is possible
FROM python:3.9.7-bullseye
# todo check if all this packages are still needed...
RUN apt-get -qq update && \
    apt-get -y install netcat libcurl4-openssl-dev libssl-dev gdal-bin libpq-dev gcc

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install python dependencies. Copy is seperated from the full src copy to cache the requirements.txt
# to avoid reinstalling requirements on every build.
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY ./entrypoint.sh .
RUN chmod +x ./entrypoint.sh

COPY ./start.sh .
RUN chmod +x ./start.sh

# copy project
COPY . .

# run entrypoint.sh
ENTRYPOINT ["/opt/mrmap/entrypoint.sh"]