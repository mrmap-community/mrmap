FROM postgis/postgis:18-3.6-alpine

# CVE-2026-111497: patch Brotli without changing the database major version.
RUN apk add --no-cache 'brotli-libs>=1.2.1-r0'
