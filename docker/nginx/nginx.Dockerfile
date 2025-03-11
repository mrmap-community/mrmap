##############################################################
# Base build Image for Frontend
##############################################################
FROM node:23-alpine3.21.3 AS frontend-compile-image

# cause env variables are always not present
# in the docker build context, we need to set them explicitly.

WORKDIR /app

COPY ./frontend/ .

# Define build arguments for environment variables
ARG VITE_API_BASE_URL
ARG VITE_API_SCHEMA

# Set environment variables during the build process
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_SCHEMA=$VITE_API_SCHEMA


RUN npm install && \
  npm run build


##############################################################
# Base build Image for Backend
##############################################################

FROM python:3.12.7-alpine3.20 AS backend-compile-image
ARG MRMAP_PRODUCTION

RUN apk update && \
  apk add --no-cache build-base gdal libressl-dev 

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY ./backend ./

RUN /usr/local/bin/python -m pip install --upgrade pip && \
  pip install -r requirements.txt && \
  python manage.py collectstatic 

##############################################################
# Default self-signed certificate generation 
##############################################################
FROM nginx:1.27.2-alpine AS cert

RUN mkdir -p /etc/ssl/private/ && \
  apk add openssl && \
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt -subj "/C=DE/ST=Rhineland-Palatinate/L=Wiesbaden/O=MrMap Community/OU=Developers/CN=example.com"


##############################################################
# Final Image
##############################################################  
FROM nginx:1.27.2-alpine-slim AS production-image

COPY --from=cert /etc/ssl/private/nginx-selfsigned.key /etc/ssl/private/nginx-selfsigned.key
COPY --from=cert /etc/ssl/certs/nginx-selfsigned.crt /etc/ssl/certs/nginx-selfsigned.crt

COPY --from=frontend-compile-image /app/dist /var/www/mrmap/frontend/
COPY --from=backend-compile-image ./static /var/www/mrmap/backend/

EXPOSE 80/tcp
EXPOSE 443/tcp