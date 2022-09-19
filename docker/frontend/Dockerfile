FROM node:16-alpine

WORKDIR /opt/mrmap

COPY ./package.json ./package-lock.json ./tsconfig.json ./

VOLUME [ "/opt/mrmap/src/.umi" ]

RUN npm install

EXPOSE 8000/tcp