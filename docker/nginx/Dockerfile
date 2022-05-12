FROM node:16-alpine as frontend-build

WORKDIR /opt/mrmap

COPY ./frontend ./

RUN npm install
RUN npm run build


FROM python:3.10.1-bullseye AS backend-build

WORKDIR /opt/mrmap

COPY ./backend ./

RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN /usr/local/bin/python -m pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements.dev.txt && \
    python manage.py collectstatic


FROM library/nginx:1.21-alpine

RUN mkdir -p /etc/ssl/private/
RUN apk add openssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt -subj "/C=DE/ST=Rhineland-Palatinate/L=Wiesbaden/O=MrMap Community/OU=Developers/CN=example.com"

COPY --from=frontend-build /opt/mrmap/dist /var/www/mrmap/frontend/
COPY --from=backend-build /var/www/mrmap/backend/ /var/www/mrmap/backend/
