FROM node:16-alpine as frontend-build

WORKDIR /opt/mrmap

COPY ./ ./

RUN npm install
RUN npm run build



FROM library/nginx:1.21-alpine

RUN mkdir -p /etc/ssl/private/
RUN apk add openssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt -subj "/C=DE/ST=Rhineland-Palatinate/L=Wiesbaden/O=MrMap Community/OU=Developers/CN=example.com"

COPY --from=frontend-build /opt/mrmap/build /var/www/mrmap/frontend/
