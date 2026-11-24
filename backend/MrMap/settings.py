"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""
import logging
import os
import re
import socket
import sys
from datetime import timedelta
from glob import glob
from urllib.parse import quote
from warnings import warn

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from django.utils.translation import gettext_lazy as _
from kombu import Exchange, Queue
from MrMap import celery_queues
from MrMap.celery import is_celery_process, is_this_a_celery_beat_process
from system.logging.formatter import RFC5424Formatter

from . import VERSION

id_extractor = re.compile(r'ID=([^^]*)')
with open('/etc/os-release', 'r') as file:
    # if we are running on alpine os, we need to pass the gdal/geos paths. Otherwise django can't find the binaries.
    for line in file:
        match = id_extractor.match(line)
        if match and "alpine" in match.groups()[0].lower():
            GDAL_LIBRARY_PATH = glob('/usr/lib/libgdal.so.*')[0]
            GEOS_LIBRARY_PATH = glob('/usr/lib/libgeos_c.so.*')[0]


def check_path_access(path: str):

    has_access = os.access(path, os.R_OK | os.X_OK | os.W_OK)
    if not os.path.exists(path) and has_access:
        os.makedirs(path)

    if not has_access:
        warn(
            message=f"no full access to path {path}. Fallback to current base directory.")
    return has_access


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Set the base directory two levels up
# this is the path where the python code is
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


################################################################
# Logger settings
################################################################

ROOT_LOGGER_NAME = "MrMap.root"

ROOT_LOGGER: logging.Logger = logging.getLogger(ROOT_LOGGER_NAME)


MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MRMAP_MEDIA_DIR", "/var/mrmap/backend/media")
MEDIA_ROOT = MEDIA_ROOT if check_path_access(
    MEDIA_ROOT) else f"{BASE_DIR}/media"


# create media dir if it does not exist
if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)

# SECURITY WARNING: don't run with debug turned on in production!
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
DEBUG = int(os.environ.get("DJANGO_DEBUG", default=0))
MRMAP_PRODUCTION = os.environ.get("MRMAP_PRODUCTION", default="False")
MRMAP_PRODUCTION = True if MRMAP_PRODUCTION == "True" else False


def _secret_key_from_env(environ, production: bool) -> str:
    """The signing key for one environment (#1473, audit SEC-12).

    A missing ``DJANGO_SECRET_KEY`` used to fall back to
    ``get_random_secret_key()`` on *every* import, which is per process and per
    boot. Under ``MRMAP_PRODUCTION`` that fallback is fatal instead: it silently
    invalidates every session, knox token and signed payload of a restarted
    deployment (a rolling restart logs all users out and rejects in-flight
    tokens), and it destroys the contents of any cache whose keys derive from
    the key. Worse, a deployment which *believes* it set the key but did not
    (renamed variable, missing ``.env``) cannot tell, because a random key works
    until the next restart. A production deployment must therefore hand over the
    key explicitly; compose already refuses to start without it
    (``${DJANGO_SECRET_KEY:?...}``), this is the same rule for every other way
    of running the application image.

    Outside production the random fallback stays: throwaway checkout and CI
    deployments which have no value to keep.
    """
    key = environ.get("DJANGO_SECRET_KEY")
    if key:
        return key
    if production:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when MRMAP_PRODUCTION is True: a "
            "random key per boot invalidates every session, token and signed "
            "payload of a restarted deployment. Set it in the deployment's "
            "environment (docs/source/development/environment.rst).")
    return get_random_secret_key()


SECRET_KEY = _secret_key_from_env(os.environ, MRMAP_PRODUCTION)


def _split_env_list(raw: str) -> list:
    """The entries of a ";"/"," separated env value, without surrounding blanks."""
    return [entry.strip() for entry in raw.replace(",", ";").split(";") if entry.strip()]


def _flag_from_env(environ, name: str, default: bool) -> bool:
    """A boolean deployment flag spelled ``"True"``/``"False"``, else the default.

    Same spelling as ``MRMAP_PRODUCTION`` itself: compose passes these values as
    strings, and any non-empty string reads as true in Python, so the string
    comparison - never ``bool(value)`` - is the whole of the parsing (#1141).
    """
    value = environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip() == "True"


# The username of the superuser this deployment seeds on migrate (accounts/
# apps.py) - a deployment value, not a code value. Named once here, because
# the account and every internal context which falls back to it (the
# service-less harvesting run of registry/models/harvest.py) have to name the
# same value; the hardcoded "mrmap" of the fallback aborted such runs on any
# deployment which named its admin differently (#1278).
MRMAP_USER = os.environ.get("MRMAP_USER")

# Application definition
INSTALLED_APPS = [
    "daphne",
    "channels",
    "guardian",
    "django.contrib.auth",
    "django.contrib.admin",  # for django admin pages
    "django.contrib.messages",  # for django admin pages
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.gis",
    "django.forms",  # for debug_toolbar and rest api html page
    "django_extensions",
    "corsheaders",
    "rest_framework",
    "rest_framework_gis",
    "rest_framework_json_api",
    "knox",  # token auth
    "django_celery_beat",
    "django_filters",
    "simple_history",
    "mptt2",
    "MrMap",  # added so we can use general commands in MrMap/management/commands
    "extras",  # to support template lookup
    "accounts",
    "registry",
    "notify",
    "csw",
    "system",
    "drf_spectacular",
    "drf_spectacular_jsonapi",
    "pgtrigger",
]

MIDDLEWARE = [
    # First, ahead of ``SecurityMiddleware``: the response phase of this
    # middleware is what answers the Content-Security-Policy of every backend
    # answer (#1473), and a middleware only sees the responses of the ones
    # *below* it - ``SecurityMiddleware`` answers its SSL redirect from inside
    # its own request phase and never calls further down, so a policy which
    # should also cover that 301 has to be listed above it. Nothing else about
    # the position matters: the middleware does nothing in the request phase.
    "MrMap.middleware.ContentSecurityPolicyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Listed above the Vary middleware, so in the response phase it runs
    # after that one and repeats the cleaned Vary on its 304 (#946).
    "extras.schema_views.SchemaConditionalGetMiddleware",
    # Below Security, above Session: strips the session marking's Vary: Cookie
    # from /api/schema responses after SessionMiddleware added it (#946).
    "extras.schema_views.SchemaVaryMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",  # for django admin pages
    # Answers ``X_FRAME_OPTIONS`` (#1473). The setting alone does nothing:
    # without this middleware the value of the knob never reaches a response,
    # which is the kind of hygiene which reads as configured and is not.
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "system.logging.middleware.LogSlowRequestsMiddleware",
]

TEMPLATE_LOADERS = "django.template.loaders.app_directories.Loader"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",  # for django admin pages
            ],
        },
    },
]

# -------------------------------
# Debug Toolbar nur aktiv, wenn DEBUG und nicht beim Testen
# -------------------------------

DEBUG_TOOLBAR_MIDDLEWARE = "debug_toolbar.middleware.DebugToolbarMiddleware"

# Which clients may see the debug toolbar when it is installed at all. The
# toolbar answers SQL, settings, request bodies and the environment of the
# request; the callback used to be ``lambda request: True``, which skipped even
# django-debug-toolbar's own INTERNAL_IPS gate and showed all of that to whoever
# reached the deployment first. Loopback only, and never under
# MRMAP_PRODUCTION - DJANGO_DEBUG alone does not make a deployment a
# development one (#1473, audit SEC-12). A developer behind a proxy which
# rewrites the client address, or a remote development machine, names its
# addresses in DJANGO_DEBUG_TOOLBAR_INTERNAL_IPS.
DEBUG_TOOLBAR_INTERNAL_IPS_DEFAULT = "127.0.0.1;::1"


def _debug_toolbar_internal_ips_from_env(environ) -> list:
    return _split_env_list(
        environ.get("DJANGO_DEBUG_TOOLBAR_INTERNAL_IPS", DEBUG_TOOLBAR_INTERNAL_IPS_DEFAULT))


DEBUG_TOOLBAR_INTERNAL_IPS = _debug_toolbar_internal_ips_from_env(os.environ)


def show_debug_toolbar(request, production=MRMAP_PRODUCTION, internal_ips=None):
    """Whether the debug toolbar may render for one request.

    The two arguments default to the module's own values so that the decision is
    testable without re-importing the settings; django-debug-toolbar calls the
    callback with the request alone.
    """
    if production:
        return False
    if internal_ips is None:
        internal_ips = DEBUG_TOOLBAR_INTERNAL_IPS
    return request.META.get("REMOTE_ADDR") in internal_ips


if DEBUG and not TESTING:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.append(DEBUG_TOOLBAR_MIDDLEWARE)

    DEBUG_TOOLBAR_CONFIG = {
        # Alle Panels standardmäßig deaktivieren
        "DISABLE_PANELS": {
            "debug_toolbar.panels.history.HistoryPanel",
            "debug_toolbar.panels.versions.VersionsPanel",
            "debug_toolbar.panels.timer.TimerPanel",
            "debug_toolbar.panels.settings.SettingsPanel",
            "debug_toolbar.panels.headers.HeadersPanel",
            "debug_toolbar.panels.request.RequestPanel",
            "debug_toolbar.panels.sql.SQLPanel",
            "debug_toolbar.panels.staticfiles.StaticFilesPanel",
            "debug_toolbar.panels.templates.TemplatesPanel",
            "debug_toolbar.panels.cache.CachePanel",
            "debug_toolbar.panels.signals.SignalsPanel",
            "debug_toolbar.panels.logging.LoggingPanel",
            "debug_toolbar.panels.redirects.RedirectsPanel",
            "debug_toolbar.panels.profiling.ProfilingPanel",
            # Problematisches Panel für binary content
            "debug_toolbar.panels.alerts.AlertsPanel",
        },
        "SHOW_TOOLBAR_CALLBACK": "MrMap.settings.show_debug_toolbar",
        "PRETTIFY_SQL": True,
    }

else:
    # Wenn DEBUG=0 oder Tests laufen, Toolbar komplett deaktivieren
    if "debug_toolbar" in INSTALLED_APPS:
        INSTALLED_APPS.remove("debug_toolbar")
    if DEBUG_TOOLBAR_MIDDLEWARE in MIDDLEWARE:
        MIDDLEWARE.remove(DEBUG_TOOLBAR_MIDDLEWARE)

# Password hashes
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

ROOT_URLCONF = "MrMap.urls"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

METADATA_URL = [
    "request=GetMetadata&",
]

# Host allow-list for Django's host validation (#949). Three sources are
# merged, every one of them optional and ";" and/or "," separated:
#  * DJANGO_ALLOWED_HOSTS: the deployer knob documented in
#    docs/source/development/environment.rst; docker-compose.yml passes it
#    through to backend, celery-worker and celery-beat.
#  * DJANGO_ALLOWED_HOST_DEFAULTS: replaces the internal preset, which keeps
#    the callers that reach the backend without a browser Host working: the
#    deployment's own service address (mrmap-appserver is the name older
#    deployments gave the app server), the dev stack publishing the backend
#    on localhost, deployments reached over the docker bridge still answer
#    to 172.17.0.1, and Django's test client sends "testserver".
#  * EXTERNAL_BASE_URL: the name the deployment is served under stays
#    auto-allowed; it may be written as a host, a host:port or a full URL
#    and contributes its bare hostname.
# CSRF_TRUSTED_ORIGINS is derived from the merged list below, so exactly the
# same hosts may POST.
ALLOWED_HOSTS_PRESET = "localhost;127.0.0.1;[::1];mrmap-appserver;172.17.0.1;testserver"


def _split_host_list(raw: str) -> list:
    """The hosts of a ";"/"," separated env value, without surrounding blanks."""
    return _split_env_list(raw)


def _bare_host(entry: str) -> str:
    """The hostname of a URL or host[:port] value, without scheme and port.

    "http://demo.mrmap.de:8000/x" and "demo.mrmap.de:8000" both yield
    "demo.mrmap.de"; a bracketed IPv6 literal keeps its brackets.
    """
    host = entry.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].rsplit("@", 1)[-1]  # drop path and credentials
    if host.startswith("["):  # bracketed IPv6, e.g. "[::1]:8000"
        return host[:host.find("]") + 1] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _allowed_hosts_from_env(environ) -> list:
    """The merged allow-list for the given environment mapping, sorted."""
    hosts = _split_host_list(environ.get("DJANGO_ALLOWED_HOST_DEFAULTS", ALLOWED_HOSTS_PRESET))
    hosts += _split_host_list(environ.get("DJANGO_ALLOWED_HOSTS", ""))
    hosts += [_bare_host(entry) for entry in _split_host_list(
        environ.get("EXTERNAL_BASE_URL", "localhost"))]
    return sorted(set(hosts))


ALLOWED_HOST_DEFAULTS = _split_host_list(os.environ.get(
    "DJANGO_ALLOWED_HOST_DEFAULTS", ALLOWED_HOSTS_PRESET))
ALLOWED_HOSTS = _allowed_hosts_from_env(os.environ)

# The vite dev server never speaks TLS, so the loopback origins of the
# development frontend are http. An http origin in the list of a *production*
# deployment is what lets a CSRF token cross the wire in clear text, which is
# why the preset only joins outside production.
CSRF_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _csrf_trusted_origins_from_env(environ, production: bool) -> list:
    """The origins whose same-origin POSTs may carry this site's CSRF token.

    These used to be derived from the merged host allow-list, for *every* entry
    and both schemes: one ``DJANGO_ALLOWED_HOSTS`` entry of a deployment added
    ``http://internal-host`` next to ``https://internal-host``, and the whole
    preset of service host names (``mrmap-appserver``, ``172.17.0.1``, ...)
    became trusted browser origins - a plaintext trust nobody chose, next to the
    http trust a production deployment must never carry (audit SEC-12, #1473).
    The explicit ``DJANGO_CSRF_TRUSTED_ORIGINS`` is now the only source a
    production deployment has, and every scheme it names is honoured - a
    deployment which serves plain https only spells out exactly that, and one
    behind a TLS terminator which forwards plain http names that origin itself.
    An unset value means django's own same-origin check and nothing else, which
    is what the same-origin topology of ``docker/nginx/mrmap.conf`` needs.
    Outside production the vite origins of the development frontend join: those
    log in through the session of this backend (#835, decision Q8=B).
    """
    origins = _split_env_list(environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", ""))
    if not production:
        origins = origins + CSRF_DEV_ORIGINS
    return sorted(set(origins))


CSRF_TRUSTED_ORIGINS = _csrf_trusted_origins_from_env(os.environ, MRMAP_PRODUCTION)


def _cors_decisions_from_env(environ, production: bool):
    """Where cross-origin requests to the API may come from for one environment.

    ``DJANGO_CORS_ALLOWED_ORIGINS`` is the only source of origins. When it is
    set, it answers in every deployment mode: the development frontend on the
    vite port and any split-origin deployment both set it. When it is empty:

    * development gets the vite loopback origins - the development frontend
      authenticates with this backend's session cookie and therefore needs
      credentialed CORS (#835);
    * production gets no cross-origin allowance at all. The shipped topology is
      same-origin - the nginx of ``docker/nginx/mrmap.conf`` serves the SPA and
      proxies ``/api``, ``/csw`` and ``/ws`` on the very host and port the SPA is
      loaded from - so there is no cross-origin consumer left to serve, and the
      previous ``CORS_ALLOW_ALL_ORIGINS = True`` let any website read the API as
      the logged-in user of any browser which visited it (audit SEC-17, #1473):
      requests authenticated by an ``Authorization`` header need no cookies at
      all, so the credentialed flag was never the guard.

    Returns ``(origins, allow_all, credentials)``. ``allow_all`` is always
    ``False``: every origin is no longer a default, it is a decision.
    """
    explicit = _split_env_list(environ.get("DJANGO_CORS_ALLOWED_ORIGINS", ""))
    if explicit:
        return sorted(set(explicit)), False, not production
    if not production:
        return sorted(set(CSRF_DEV_ORIGINS)), False, True
    return [], False, False


CORS_ALLOWED_ORIGINS, CORS_ALLOW_ALL_ORIGINS, CORS_ALLOW_CREDENTIALS = _cors_decisions_from_env(
    os.environ, MRMAP_PRODUCTION)
if not CORS_ALLOWED_ORIGINS:
    warn(
        "no CORS origins are allowed: no cross-origin consumer may call the API. "
        "Set DJANGO_CORS_ALLOWED_ORIGINS if a frontend is served from another "
        "origin than the backend (docs/source/development/environment.rst).")

USE_X_FORWARDED_HOST = True
# What makes both of the following trust the reverse proxy rather than the
# client: this exact pair. ``USE_X_FORWARDED_HOST`` makes the ``Host`` header
# of the proxy authoritative, ``SECURE_PROXY_SSL_HEADER`` makes the protocol
# of the *proxy* authoritative - and only when the named header carries the
# named value, so a client which forges ``X-Forwarded-Proto`` on a direct
# connection gets no say. Both of them are only honest while the edge really
# sets what it forwards: the nginx of ``docker/nginx/mrmap.conf`` normalizes
# ``X-Forwarded-Proto`` with a ``map`` instead of passing the client value
# through verbatim, and a deployment with another edge in front owes the same
# normalization, or it reads its own https traffic as plain http and the SSL
# redirect below 301s it in a loop. See
# docs/source/development/environment.rst, ``DJANGO_SECURE_SSL_REDIRECT``.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

################################################################
# HTTP transport security (#1473, audit SEC-12)
################################################################
# The hardening Django ships, gated on MRMAP_PRODUCTION: the deployment this
# repository ships runs behind nginx and TLS, so a production deployment gets
# the whole block by default and an http-only development stack must not even
# try it - a redirect to https the dev stack does not speak would just break
# it. Each setting is overridable on its own, because a deployment in front of
# a TLS terminator which cannot serve HSTS, or one which terminates TLS
# itself, needs to narrow the block without dropping the rest.
#
# ``SECURE_SSL_REDIRECT`` is the one knob of the block which can take a
# deployment down: with ``MRMAP_PRODUCTION`` a plain-http request is 301'd to
# https, which is only correct when a TLS endpoint really answers that https
# *and* names the protocol to Django - see the ``SECURE_PROXY_SSL_HEADER``
# note above. A deployment whose TLS dies in front of this container and which
# wants to answer plain http sets ``DJANGO_SECURE_SSL_REDIRECT=False``.
SECURE_SSL_REDIRECT = _flag_from_env(os.environ, "DJANGO_SECURE_SSL_REDIRECT", MRMAP_PRODUCTION)


def _hsts_seconds_from_env(environ, production: bool) -> int:
    """The HSTS ``max-age`` of one environment, in seconds.

    Blank means the default of the deployment mode, as it does for every other
    knob of the block. A value which is not a number is refused while the
    settings load rather than being read as some other number elsewhere: the
    header is a one-way door once a browser has seen it, so a deployment which
    meant a year and typed ``1y`` must not find out from a browser which refuses
    http to its host, and must not silently get the mode's default either.
    """
    raw = environ.get("DJANGO_SECURE_HSTS_SECONDS")
    if raw is None or not raw.strip():
        return 31536000 if production else 0
    value = raw.strip()
    # not int(value): int() also swallows the underscore separators of a Python
    # literal, so a deployment which typed 1_000_000 would get what it typed
    # while believing it had named a value no one else reads the same way
    if not re.fullmatch(r"-?\d+", value):
        raise ImproperlyConfigured(
            f"DJANGO_SECURE_HSTS_SECONDS must be a number of seconds, got "
            f"{raw!r}. Set 0 to send no Strict-Transport-Security header at all.")
    seconds = int(value)
    if seconds < 0:
        raise ImproperlyConfigured(
            f"DJANGO_SECURE_HSTS_SECONDS must not be negative, got {seconds}. "
            "Set 0 to send no Strict-Transport-Security header at all.")
    return seconds


SECURE_HSTS_SECONDS = _hsts_seconds_from_env(os.environ, MRMAP_PRODUCTION)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _flag_from_env(
    os.environ, "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", MRMAP_PRODUCTION)
SECURE_HSTS_PRELOAD = _flag_from_env(os.environ, "DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = _flag_from_env(
    os.environ, "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", True)
SECURE_REFERRER_POLICY = (
    os.environ.get("DJANGO_SECURE_REFERRER_POLICY") or "same-origin")
# A browser must only ever frame this application's own pages. Django's
# middleware answers the header; the edge of the frontend repeats it
# (docker/nginx/mrmap.conf) for the answers it serves itself.
X_FRAME_OPTIONS = os.environ.get("DJANGO_X_FRAME_OPTIONS") or "DENY"
if SECURE_SSL_REDIRECT and SECURE_HSTS_SECONDS == 0:
    warn(
        "SECURE_SSL_REDIRECT is active with an HSTS max-age of 0: the browser "
        "may still talk plain http to this deployment tomorrow. Set "
        "DJANGO_SECURE_HSTS_SECONDS or disable the redirect.")

################################################################
# Content-Security-Policy (#1473, audit SEC-17)
################################################################
# Which sources a browser may load this application from. The audit opened
# this because the knox token of the token login lives in ``localStorage``
# and any injected script can read it - and after #835 the browser session
# joined it, so the one XSS that reads the token also rides the session
# cookie, and no SameSite or HttpOnly flag of the cookie block above helps
# against script which runs *in* the page. CSP is the layer which makes
# injected script unable to do anything with what it read: it may not fetch
# an address, post to a collector, or phone home at all, because every
# outbound load has to be a source this list names.
#
# The policy answers the backend's own answers - XML documents of the OGC
# endpoints, error pages, the browsable API of a development deployment. The
# SPA and its own assets are answered by nginx, whose edge carries the same
# policy (docker/nginx/mrmap.conf); both lists are written from the same
# facts: the references of frontend/index.html (leaflet and leaflet-geoman
# from unpkg, the Roboto stylesheet from the Google Fonts CDN) and what the
# built bundle loads itself (the monaco editor from jsDelivr, the map tiles
# of the record editor from the OSM tile hosts).
#
# ``connect-src`` carries no ``wss:``. That spelling is a *scheme* source -- a
# source with a scheme and no host -- so it admits ``wss://`` to every address
# there is, which is the outbound channel this header exists to close: injected
# script which had read a credential would be free to post it to a collector, and
# from a browser inside a company network to ``wss://10.0.0.7:PORT`` as well,
# which is a pivot towards hosts the deployment can reach and the public cannot.
# The application does not need the breadth: the only socket it opens is its own
# origin (``RealtimeBus.tsx`` builds it from ``VITE_API_BASE_URL`` /
# ``VITE_API_PORT``, which ``docker-compose.yml`` feeds from ``EXTERNAL_BASE_URL``
# / ``EXTERNAL_PORT`` -- the very host and port the SPA was loaded from), and CSP
# normalizes ``wss`` to ``https`` when it matches a source, so ``'self'`` admits
# it. Where a socket really leaves the origin, it is a development decision and
# joins below, the way the vite origins join ``CSRF_TRUSTED_ORIGINS``.
#
# ``'unsafe-inline'`` for styles is not a hole: the styling-in-CSS and
# inline-style attributes of MUI, leaflet and monaco are the mechanism those
# libraries position map overlays and editor decorations with, and CSP
# governs script much more than style - inline style cannot read a token and
# cannot reach the network. Scripts stay without it, which is the whole
# point. ``blob:`` for images and workers is what the preview overlays
# (``URL.createObjectURL``) and library worker bootstraps need; a blob URL
# is same-origin and its script is bound by this very policy. The third-party
# *image* source is the basemap of the record editor (``GeoJsonMap`` and
# ``CoverageMap`` load OSM tiles); an image load cannot read its own answer,
# so it is not the channel this header exists to close, and naming it keeps
# the shipped deployment working. The authenticated OGC answers are not here
# at all on purpose: the SPA fetches them through ``/mrmap-proxy`` - same
# origin, covered by ``'self'`` - and draws them from a blob URL.
CSP_DEFAULT = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https://unpkg.com https://*.tile.openstreetmap.org; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
# A deployment which is served over TLS (the SSL redirect above is on) tells
# the browser to upgrade anything it still loads over plain http, so a
# stored ``http://`` resource reference cannot be downgraded on the wire.
CSP_UPGRADE_INSECURE = "; upgrade-insecure-requests"
# Sockets a development deployment opens outside the page's own origin, and the
# origin of the vite dev server which opens them. The vite server proxies nothing
# (``frontend/vite.config.mjs`` has no ``server.proxy``), so a page served from
# ``:5173`` reaches the API and the websocket of the backend on ``:8001`` - two
# origins, both loopback, both spelled out here instead of bought with a
# ``wss:`` that would also be in force in production. The shipped deployment
# needs neither: its edge serves the SPA and proxies ``/ws/`` on one origin.
CSP_DEV_CONNECT_SRC = "ws://localhost:8001 ws://127.0.0.1:8001"


def _shipped_policy_has_no_wildcard_socket(policy: str) -> str:
    """Refuse a shipped policy whose ``connect-src`` carries a scheme source.

    A source with a scheme and no host (``wss:``, ``ws:``) matches that scheme to
    every address, which is the channel the policy exists to close. The guard
    covers what this repository ships in either deployment mode - not
    ``DJANGO_CONTENT_SECURITY_POLICY``, which is an operator naming their own
    complete policy and stays their decision.
    """
    for part in policy.split(";"):
        directive = part.strip()
        if not directive.startswith("connect-src"):
            continue
        offenders = [source for source in directive.split()[1:]
                     if source.endswith(":") and not source.startswith("'")]
        if offenders:
            raise ImproperlyConfigured(
                f"{', '.join(offenders)} in connect-src is a scheme source: it "
                "admits that scheme to every host, which is the outbound channel "
                "this policy exists to close. Name the origin of the socket "
                "instead, or - for a development-only socket - add it to "
                "CSP_DEV_CONNECT_SRC.")
    return policy


def _content_security_policy_from_env(environ, production: bool) -> str:
    """The Content-Security-Policy header value of a deployment.

    ``DJANGO_CONTENT_SECURITY_POLICY`` replaces the whole policy verbatim -
    a deployment which embeds its own map viewer in an iframe, loads the SPA
    from another host or runs a frontend which needs another source names
    its complete policy there. An empty value turns the header off for the
    backend's own answers; the edge of ``docker/nginx/mrmap.conf`` keeps
    serving its own copy for the SPA, so "off" here never means "unprotected
    deployment".

    The shipped default is served in every deployment mode: it documents the
    sources of this application, not a production decision, and a policy
    which is only ever exercised in production is a policy whose breakage is
    discovered in production. Only the two loopback sockets of the vite dev
    server join outside production, because that is the one topology where a
    socket leaves the page's origin; production gets ``connect-src 'self'`` and
    nothing else. Neither shipped policy may carry a bare ``ws:``/``wss:``,
    which the guard below refuses at import rather than in a browser.
    ``upgrade-insecure-requests`` joins under
    ``MRMAP_PRODUCTION``, where the TLS of the deployment is a promise.
    """
    explicit = environ.get("DJANGO_CONTENT_SECURITY_POLICY")
    if explicit is not None:
        return explicit.strip()
    policy = CSP_DEFAULT
    if not production:
        policy = policy.replace(
            "connect-src 'self';", f"connect-src 'self' {CSP_DEV_CONNECT_SRC};")
    policy += CSP_UPGRADE_INSECURE if production else ""
    return _shipped_policy_has_no_wildcard_socket(policy)


CONTENT_SECURITY_POLICY = _content_security_policy_from_env(
    os.environ, MRMAP_PRODUCTION)


# GIT repo links
GIT_REPO_URI = "https://github.com/mrmap-community/mrmap"
GIT_GRAPH_URI = "https://github.com/mrmap-community/mrmap/graph"

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/
LANGUAGE_CODE = "en"
LANGUAGES = (
    ("en", _("English")),
    ("de", _("German")),
)
LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"),)
DEFAULT_DATE_TIME_FORMAT = "YYYY-MM-DD hh:mm:ss"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Europe/Berlin")
USE_I18N = True
USE_L10N = True
USE_TZ = True

# configure your proxy like "http://10.0.0.1:8080"
# or with username and password: "http://username:password@10.0.0.1:8080"
PROXIES = {
    "no_proxy": os.getenv("no_proxy", os.getenv("NO_PROXY", "")),
    "http": os.getenv("http_proxy", os.getenv("HTTP_PROXY", "")),
    "https": os.getenv("https_proxy", os.getenv("HTTPS_PROXY", "")),
}

# configure if you want to validate ssl certificates
# it is highly recommend keeping this to true
VERIFY_SSL_CERTIFICATES = True

# django-guardian

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",  # default
    "guardian.backends.ObjectPermissionBackend",
)

GUARDIAN_RAISE_403 = True

#: The models whose list endpoints answer permission-filtered (#739), as
#: ``"<app_label>.<ModelName>"`` names - the same spelling as
#: ``accounts.settings.ROLE_MANAGED_MODELS``. An entry makes every list,
#: detail and search over that resource answer exactly the rows which
#: ``extras.permissions.objects_for_user`` passes: an anonymous visitor
#: lists only the resources with an explicit grant to the anonymous viewer
#: role group, a member lists within their roles - in SQL, before the page
#: and its count are decided. Empty is today's behaviour kept: the list
#: answers everything and only the detail endpoint decides.
#:
#: The rollout is deliberately per model and opt-in (decision Q5=B of #727):
#: a deployment enables a resource only after it has inventoried which of
#: its resources were publicly listed under the unfiltered list and has run
#: the audited legacy-grant migration of #740, because enabling narrows
#: what anonymous visitors and foreign members see and that transition has
#: to be reviewed, never an upgrade side effect. Enabling an entry whose
#: model is not equipped is refused by the system check of
#: ``accounts/checks.py``; the reading is in
#: ``docs/source/administration/permissions.md``.
PERMISSION_FILTERED_LIST_MODELS = [
    name.strip() for name in
    os.getenv("MRMAP_PERMISSION_FILTERED_LIST_MODELS", "").split(",")
    if name.strip()]

################################################################
# Database settings
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases
################################################################
# There used to be a second pair of numbers here (RESERVED_CONNECTION_SPACE
# and a MAX_BACKEND_RESERVED_CONNECTIONS of 10) which no code read while the
# environment of the same name answered 20 - #1621 removed the copy, one
# source of truth is below.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("SQL_ENGINE", "django.contrib.gis.db.backends.postgis"),
        "NAME": os.environ.get("SQL_DATABASE", "mrmap"),
        "USER": os.environ.get("SQL_USER"),
        "PASSWORD": os.environ.get("SQL_PASSWORD"),
        "HOST": os.environ.get("SQL_HOST", "localhost"),
        "PORT": os.environ.get("SQL_PORT", "5432"),
        "CONN_HEALTH_CHECKS": True,
    }
}


# -------------------------
# Pooling for normale Requests
# -------------------------
def _pool_int_from_env(name, environ, default):
    """One bound of the HTTP tier's connection pool, read from the deployment.

    An absent or empty value answers ``default``; anything else has to be an
    integer of at least 1, and both other answers raise while the settings
    load. #1615's lesson applies to this knob class as well: a number the
    deployment sets and the process then reads differently than meant is
    worse than no knob, because it is the number an operator trusts. The
    floor is the pool's own - psycopg refuses a min or max size below 1.
    """
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name}={raw!r} is not an integer") from None
    if value < 1:
        raise ValueError(
            f"{name}={raw!r} is below 1: the psycopg pool refuses 0, so this "
            "knob has no spelling of 'off' - leave it empty for the default "
            "of the selected mode "
            "(docs/source/development/environment.rst)")
    return value


def _db_pool_bounds_from_env(environ):
    """The pool bounds of every non-celery process, from one place (#1621).

    ``MRMAP_LOW_MEMORY`` selects the mode with the spellings
    ``backend/.bash_scripts/process_defaults.sh`` uses, so the web tier's
    process shape and its per-process connection reservation move together
    and cannot drift apart: the shipped shape runs four HTTP workers which
    each reserve four pooled connections at rest, the low-memory shape runs
    one worker with two request threads and reserves one, capped at four.
    Explicit bounds win over the mode, exactly as an explicit
    ``GUNICORN_WORKERS`` wins over it.

    The ceiling bounds the growth of one process, not the deployment's
    total: four HTTP workers with max_size 20 could together outgrow the 100
    connections PostGIS answers by default, which is why a capacity-aware
    deployment sets the pair rather than trusting the preset. The live
    readings of idle and loaded pool sizes and of PostgreSQL's own memory
    per connection are in
    ``docs/source/development/db-pool-memory.rst``.
    """
    low_memory = (environ.get("MRMAP_LOW_MEMORY") or "").strip().lower() \
        in ("1", "true", "yes", "on")
    default_min, default_max = (1, 4) if low_memory else (4, 20)
    min_size = _pool_int_from_env(
        "MIN_BACKEND_RESERVED_CONNECTIONS", environ, default_min)
    max_size = _pool_int_from_env(
        "MAX_BACKEND_RESERVED_CONNECTIONS", environ, default_max)
    if min_size > max_size:
        raise ValueError(
            f"MIN_BACKEND_RESERVED_CONNECTIONS={min_size} exceeds "
            f"MAX_BACKEND_RESERVED_CONNECTIONS={max_size}: the pool cannot "
            "reserve more connections than it is allowed to open")
    return min_size, max_size


_DB_POOL_MIN_SIZE, _DB_POOL_MAX_SIZE = _db_pool_bounds_from_env(os.environ)
if not is_celery_process():
    DATABASES["default"]["OPTIONS"] = {
        "pool": {
            "min_size": _DB_POOL_MIN_SIZE,
            "max_size": _DB_POOL_MAX_SIZE,
            "timeout": 30,
        }
    }

# -------------------------
# Celery-Worker ohne Pool
# -------------------------
# Note!!: do not activate pooling for any celery purpose.
# It caused more problems then benefits.
# It happend many times, that there are old unfinished transactions in a pooled connection, which caused different sql errors..
# So we only use pool for normal backend
SYSTEM_STATUS_BEAT_APPLICATION_NAME = "mrmap-celery-beat"
if is_celery_process():
    if is_this_a_celery_beat_process():
        # Identify Beat's existing session without a heartbeat or extra service.
        DATABASES["default"]["OPTIONS"] = {
            "application_name": SYSTEM_STATUS_BEAT_APPLICATION_NAME,
        }
    else:
        # Worker: kein Pool, jede Task nutzt eigene Connection
        DATABASES["default"]["OPTIONS"] = {}

# To avoid unwanted migrations in the future, either explicitly set DEFAULT_AUTO_FIELD to AutoField:
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
################################################################
# Redis settings
################################################################
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

# Authentication of the shared instance (#1473, audit SEC-17). The instance is
# the celery broker, the celery result backend and the Django cache at once,
# so *any* client which reaches its port can enqueue work this fleet executes,
# read task results, or flush the queue and the cache - the broker contract of
# #1618, that queued work survives, is worthless while an unauthenticated port
# exists. The redis service of docker-compose.yml therefore starts with
# ``--requirepass`` from ``${REDIS_PASSWORD:?...}``: the same channel the
# maxmemory bound of #1618 uses, because redis expands no variable inside its
# config file and a committed file is no place for a secret anyway. Every
# client of this project authenticates with the same variable - celery, its
# result backend and the Django cache through the userinfo of the URLs below
# (redis-py percent-decodes them), the channel layer through the ``password``
# option of its host entry. An empty value means "no auth", the contract of a
# development stack which shares its broker with nothing else; the shipped
# production stack requires the variable at compose level.
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")


def _redis_url_authority(password: str, host: str, port: str) -> str:
    """The ``host:port`` of a Redis URL, with the password as userinfo.

    The percent-encoding is the one kombu's ``maybe_unquote`` undoes
    (kombu/utils/urls.py): unreserved characters and ``!$&()*+,;=`` pass
    through a URL userinfo unquoted, so only what is reserved there is
    encoded - encoding any other byte would hand Redis a literal percent
    sign. Logging is not the reason to be careful with the value: kombu
    masks the userinfo of a broker URL in its own log and exception lines
    (``kombu.connection.Connection.as_uri``). The encoding matters because
    a special character which is *not* encoded silently changes the host the
    client connects to, which is a connection failure nobody can read.
    """
    userinfo = f":{quote(password, safe='!$&()*+,;=')}@" if password else ""
    return f"{userinfo}{host}:{port}"


# The URL of the instance every Redis client of the project talks to, auth
# included. An empty password yields the plain ``host:port`` form: no auth,
# which stays the contract of the development stack. The database number is
# appended by the consumers (``/0`` for celery, ``/1`` for the cache), which
# is why this ends with the port.
BROKER_URL = f"redis://{_redis_url_authority(REDIS_PASSWORD, REDIS_HOST, REDIS_PORT)}"

# Cache
# Use local redis installation as cache
# The "regular" redis cache will be set to work in redis table 1 (see LOCATION)
# The default table (0) is preserved for celery task management
#
# Memory policy of the shared instance (#1618): the redis service runs bounded
# with maxmemory-policy volatile-lru (docker/redis/redis.conf, maxmemory from
# REDIS_MAXMEMORY in docker-compose.yml). Redis cannot bound a single table, so
# one policy covers the whole instance and the separation is done by what
# expires: every writer of this cache passes a finite timeout - the leases of
# ``extras.locks``, the capacity snapshots of ``system``, the harvesting
# fingerprint - so all cache keys are evictable and give way under pressure,
# while the broker's queue and unacked lists of table 0 carry no expiry and can
# therefore never become eviction victims. Two caches are deliberately not on
# Redis and so not at risk of the bound at all: the schema document of
# ``extras.schema_views`` is a ``timeout=None`` write and lives in
# ``local-memory`` below, and the XML cache of the mappers is process-local. A
# store with ``timeout=None`` on Redis would be exempt from eviction - none of
# this project's Redis writers does that today, and one added later must be
# weighed against the bound. ``IGNORE_EXCEPTIONS`` is deliberately not enabled:
# a cache write refused at the limit has to surface, not be swallowed as a miss.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{BROKER_URL}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        },
    },
    "local-memory": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    },
}


################################################################
# Celery settings
################################################################
def _worker_int_from_env(name, environ, default=None):
    """One integer knob of the worker fleet, read from the deployment.

    An absent or empty value answers ``default``. Anything else has to be an
    integer of at least 1, and both other answers raise while the settings
    load. The floor is not a preference: the worker command reads the very same
    variable from the environment itself (the click option
    ``--max-tasks-per-child``, ``celery/bin/worker.py``) and hands it to the
    prefork pool as it stands, where 0 is refused with "maxtasksperchild must
    be a positive int or None" - measured with the celery 5.7.0 of the image,
    and the reason 0 is not this project's spelling of "off". A number a
    deployment sets and the fleet then reads differently than the deployment
    meant is the failure #1615 is about, so it is worth the loud start-up.
    """
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name}={raw!r} is not an integer") from None
    if value < 1:
        raise ValueError(
            f"{name}={raw!r} is below 1: the prefork pool refuses 0, so this "
            "knob has no spelling of 'off' - leave it empty for the default of "
            "the release (docs/source/development/environment.rst)")
    return value


CELERY_BROKER_URL = BROKER_URL
# Celery's native Redis result backend (celery.backends.redis:RedisBackend),
# on the table the comment above preserves for celery task management: task
# results, group metadata and the chord bookkeeping live there under celery's
# own ``celery-task-meta-``/``celery-taskset-meta-`` prefixes, next to the
# broker's keys and apart from the Django cache in table 1. The former
# ``extras.celery:RetryingCacheBackend`` wrapper over the package
# django-celery-results is removed (#1178); the native backend is what keeps
# results in Redis for the chords of registration and harvesting.
CELERY_RESULT_BACKEND = f"{BROKER_URL}/0"
# Chord members must store results. A Redis read or write that fails with a
# connection error is retried here, after the task body has completed, rather
# than failing or rerunning the harvest: the native backend treats Redis
# connection and timeout errors as safe to retry, and any other error - a
# programming error - is raised at once instead of being retried (#816's
# regression intent, kept by tests/django/test_celery_backend.py). A write
# first runs through the backend's own bounded connection-retry loop; these
# are the retries of the outer loop with exponential backoff, and an exhausted
# budget surfaces as a BackendStoreError in the worker log, not as a task-body
# failure.
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# How long results and chord bookkeeping live (celery's default of one day,
# spelled out because the harvest's import chord is the long-running chord
# this budget must cover): every part returning from the backlog refreshes the
# expiry of the group's keys, so a chord which keeps working for hours does
# not lose its bookkeeping, while the keys of a chord that died expire on
# their own instead of filling Redis.
CELERY_RESULT_EXPIRES = 60 * 60 * 24
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_RESULT_EXTENDED = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
RESPONSE_CACHE_TIME = 60 * 30  # 30 minutes
CELERY_TASK_DEFAULT_QUEUE = celery_queues.DEFAULT
CELERY_TASK_DEFAULT_EXCHANGE = celery_queues.DEFAULT

# Recycling of one prefork child (#1615). The name this file carried for the
# knob, CELERY_MAX_TASKS_PER_CHILD, is not a setting of the celery the project
# runs: measured against the installed celery 5.7.0, the key of
# celery.app.defaults.DEFAULTS is 'worker_max_tasks_per_child' and there is no
# 'max_tasks_per_child' at all, so the namespace CELERY wrote the value onto a
# key no reader exists for while app.conf answered the live name as None. The
# fleet therefore never replaced a child, whatever the deployment believed it
# asked for. The knob below is spelled the way celery spells it and is a
# deployer knob like the number of slots (#1454): the release asks for 1000 and
# a deployment may name any other positive number. There is no number of this
# variable which means "never" - the worker command reads the variable from the
# environment itself and 0 stops the pool at start-up - so turning recycling
# off is not what an empty value does here; empty is the 1000 of the release.
CELERY_WORKER_MAX_TASKS_PER_CHILD = _worker_int_from_env(
    "CELERY_WORKER_MAX_TASKS_PER_CHILD", os.environ, 1000)
# The memory of one child, in kB, at which the pool replaces it. Off in the
# release for two measured reasons. The quantity celery compares is
# getrusage(RUSAGE_SELF).ru_maxrss - the highest resident set the child ever
# reached, shared pages included (billiard/compat.py) - and a fresh child of
# this project already peaks near 170 MB of it, so a bound below the peak the
# deployment's own import reaches (211 MB over 2400 imported documents, see
# docs/source/development/celery-queues.rst) bounds nothing: it replaces the
# child after every task. And the check runs only after a COMPLETED task
# (billiard/pool.py), so it is no OOM guard either - the attempt which
# allocates past its container never meets the bound. That one child holds 211
# MB and no more after the biggest import the release measured is what lets the
# fleet run without this bound. A deployment which has watched its children
# names the kB it wants; the tests of
# tests.django.test_celery_worker_config keep both recycling names on celery's
# real table, so a renamed knob can not go inert a second time.
CELERY_WORKER_MAX_MEMORY_PER_CHILD = _worker_int_from_env(
    "CELERY_WORKER_MAX_MEMORY_PER_CHILD", os.environ)
# The window of revoked task ids is deliberately NOT a setting of this file.
# celery builds it in celery/worker/state.py from the environment variable of
# this name (`REVOKES_MAX = _int_env('CELERY_WORKER_REVOKES_MAX', 50000)`), so
# the CELERY_WORKER_REVOKES_MAX = 2000000 this file carried was inert like the
# recycling knob above: the window stayed at celery's 50000. That is not a
# number only bookkeepers care about - the abort of a BKG sized harvest revokes
# well past it (over 600000 queued ids, registry/models/harvest.py), and a
# revocation the window already forgot is a message which runs again.
# docker-compose.yml hands the variable to the worker service, which is where
# state.py reads it.

# One un-acked message per slot at any time (#1454). The long work of this
# fleet runs with acks_late (HarvestingTask of registry/tasks/harvest.py,
# the WMS update job of registry/tasks/update.py): its message stays
# un-acked while the task works, and celery's default prefetch of four per
# slot lets a worker reserve three further messages beside the one it runs.
# On every roll or restart those reserved, never-started messages are
# requeued and their side effects run again from the start - for the
# harvesting, registration and update tasks that is a second download and
# import of work nobody had begun. Celery's own configuration docs
# prescribe 1 for a worker running tasks with side effects; the broker
# round trip it costs per message is the price of not re-executing work.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Global bounds of one task attempt (#1454). The longest single request the
# deployment runs on purpose is a harvesting GetRecords, bounded by
# HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS (900 s, registry/settings.py); the
# soft limit at three times that ceiling leaves room for the parse and the
# persist around a healthy request and cuts the CPU-bound parse/import and
# mapping recursion which would otherwise pin a slot forever. On the soft
# limit celery raises SoftTimeLimitExceeded inside the task, so the body's
# cleanup and the failure paths of its base class still run and a bounded
# wait like the lease wait of registry/tasks/service.py ends decided; the
# hard limit SIGKILLs the slot a further five minutes later and the prefork
# pool replaces it. A hard-killed attempt leaves an open row in the attempt
# samples of #1330, which the sweep flags abandoned only after
# CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS. Time limits belong to the prefork
# pool, which is what the celery-worker of docker-compose.yml runs.
CELERY_TASK_SOFT_TIME_LIMIT = 2700
CELERY_TASK_TIME_LIMIT = 3000
# the number of slots a celery worker process runs; docker-compose.yml hands
# the variable of the same name from the .env of the deployment to
# celery-worker. Unset, the compose file of a release now defaults the worker
# to 4 slots (#1454): an inherited one-slot-per-host-core prefork pool
# against the memory limit of the container was the OOM path behind stuck
# jobs. "auto" lets celery size the prefork pool by the cgroup quota of the
# container; a deployment which really wants celery's own default can still
# pass an empty value with its own override. It is the knob for a bigger
# worker, so that changing worker concurrency never makes a deployment
# restate the queue list of the release and thereby half-install it (#1040).
_CELERY_WORKER_CONCURRENCY = os.environ.get("CELERY_WORKER_CONCURRENCY", "").strip()
if _CELERY_WORKER_CONCURRENCY == "auto":
    CELERY_WORKER_CONCURRENCY = "auto"
elif _CELERY_WORKER_CONCURRENCY:
    CELERY_WORKER_CONCURRENCY = int(_CELERY_WORKER_CONCURRENCY)
else:
    CELERY_WORKER_CONCURRENCY = None
CELERY_TASK_QUEUES = (
    Queue(
        name=celery_queues.DEFAULT,
        exchange=Exchange(celery_queues.DEFAULT),
        routing_key=celery_queues.DEFAULT,
        max_priority=10,
    ),
    Queue(
        name=celery_queues.DOWNLOAD,
        exchange=Exchange(celery_queues.DOWNLOAD),
        routing_key=celery_queues.DOWNLOAD,
        max_priority=3,
    ),
    Queue(
        name=celery_queues.DB_ROUTINES,
        exchange=Exchange(celery_queues.DB_ROUTINES),
        routing_key=celery_queues.DB_ROUTINES,
        max_priority=6,
    ),
    Queue(
        # the import backlog of a harvest, kept off db-routines so that the
        # chord control, the background process callbacks and the beat
        # scheduled tasks there stay reachable while a catalogue drains
        # through this queue (#970)
        name=celery_queues.HARVEST_IMPORT,
        exchange=Exchange(celery_queues.HARVEST_IMPORT),
        routing_key=celery_queues.HARVEST_IMPORT,
        max_priority=6,
    ),
    Queue(
        name=celery_queues.MONITORING,
        exchange=Exchange(celery_queues.MONITORING),
        routing_key=celery_queues.MONITORING,
        max_priority=5,
    ),
    Queue(
        name=celery_queues.UPDATE,
        exchange=Exchange(celery_queues.UPDATE),
        routing_key=celery_queues.UPDATE,
        max_priority=4,
    ),
)

################################################################
# Celery capacity telemetry (#1330)
################################################################
# The bounded attempt samples the capacity snapshots of #1326 read: every
# worker records per attempt how long it really occupied a slot and, when the
# message carried the publish stamp, how long it had waited in the broker.
# The collector never blocks the task it observes: it buffers in the worker
# process, writes in batches of at most FLUSH_THRESHOLD attempts, and goes
# quiet for a cooldown when the database does not answer. The limits below
# bound the buffer, the table and the retention; what they cost in honesty is
# stated openly - dropped or abandoned attempts are missing samples, never
# invented ones (docs/source/development/celery-capacity-telemetry.rst).
# "off" turns the whole collection and the publish stamping off; on is the
# default because the measurement is what #1326 needs to become truthful.
CAPACITY_TELEMETRY_ENABLED = os.environ.get(
    "MRMAP_CAPACITY_TELEMETRY", "").strip().lower() not in (
    "off", "0", "false")
# tests which drive the celery signals by hand set this to record outside of
# real worker processes; a deployment must leave it False
CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS = False
# attempts a worker process keeps before its buffer starts dropping open
# observations under overload (drops are counted and logged, #1330)
CAPACITY_TELEMETRY_BUFFER_LIMIT = 1000
# buffered attempts that trigger a batched write, and the maximum age of a
# buffered attempt before the next signal flushes - one INSERT per batch
CAPACITY_TELEMETRY_FLUSH_THRESHOLD = 100
CAPACITY_TELEMETRY_FLUSH_SECONDS = 30
# how long a failed flush silences the collector instead of retrying per task
CAPACITY_TELEMETRY_RETRY_COOLDOWN_SECONDS = 60
# the sweep of system.tasks keeps the table bounded by these two bounds; the
# grace must stay above the longest task this deployment runs on purpose,
# because an attempt without an end within the grace is declared abandoned
CAPACITY_TELEMETRY_RETENTION_DAYS = 14
CAPACITY_TELEMETRY_MAX_ATTEMPTS = 200_000
CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS = 48
# the bounded opt-in root-cause profiling of slow tasks (#1389, epic #1387
# V2): OFF by default and only ever on for an allowlist of task names, so a
# deployment enables it deliberately per operator decision. Categories are
# process-local and read in batches - enabling this never adds a synchronous
# per-task database write.
TASK_PROFILING_ENABLED = os.environ.get(
    "MRMAP_TASK_PROFILING", "").strip().lower() in ("on", "1", "true")
# comma separated celery task names to profile; empty means nothing, even
# when the mode is on (fail-safe default)
TASK_PROFILING_TASKS = [
    name.strip() for name in os.environ.get(
        "MRMAP_TASK_PROFILING_TASKS", "").split(",") if name.strip()]
# fraction of a profiled task's attempts which get a profile, decided
# stably from the task uuid (#1389: sampled, not everything)
TASK_PROFILING_SAMPLE_RATE = float(
    os.environ.get("MRMAP_TASK_PROFILING_SAMPLE_RATE", "0.05") or 0.0)
# buffered profiles per worker process; an overflow marks the dropped
# profile partial and counts the drop, never blocks the task
TASK_PROFILING_BUFFER_LIMIT = 200
# the broker round trip of the topology inspect and how long its answer is
# shared, so a snapshot request never pays for a broadcast
CAPACITY_TOPOLOGY_CACHE_SECONDS = 60
CAPACITY_TOPOLOGY_TIMEOUT_SECONDS = 1.0
# the capacity snapshot of #1326 is a materialized answer, not a per-request
# scan: it is built at most once per interval and served from the cache until
# its TTL expires or the schedules it counted have demonstrably changed
# (schedule fingerprint below). The walk budgets are the worst case of one
# build; a deployment that outruns them gets a labeled lower bound, never a
# silently truncated number.
CAPACITY_SNAPSHOT_TTL_SECONDS = 900
CAPACITY_SNAPSHOT_HORIZON_DAYS = 7
CAPACITY_SNAPSHOT_MAX_HORIZON_DAYS = 31
# the shared verdict of "a build is running" and the shortest distance two
# builds may have, so a busy fleet of readers cannot stack refreshes
CAPACITY_SNAPSHOT_BUILD_LOCK_SECONDS = 300
CAPACITY_SNAPSHOT_MIN_REBUILD_SECONDS = 60
# how often the schedule fingerprint may be re-read: one bounded aggregate
# statement per this interval, shared by every reader of the endpoint
CAPACITY_FINGERPRINT_CACHE_SECONDS = 30
# the horizon histogram: bucket width and the resulting bucket cap
# (horizon 7 d at 3600 s = 168 buckets; the cap bounds 31 d horizons)
CAPACITY_SNAPSHOT_BUCKET_SECONDS = 3600
CAPACITY_SNAPSHOT_MAX_BUCKETS = 744
# walk budgets of one build; over them the walk stops and the affected
# schedules are reported as truncated, keeping the build cost bounded
CAPACITY_SNAPSHOT_MAX_SCHEDULES = 100_000
CAPACITY_SNAPSHOT_MAX_OCCURRENCES = 2_000_000
CAPACITY_SNAPSHOT_MAX_OCCURRENCES_PER_SETTING = 20_000
# the window the per-occurrence costs are measured from, and how few terminal
# samples a name may answer a mean cost from; fewer answer no cost, which
# keeps the demand a labeled lower bound instead of a guess
CAPACITY_COST_LOOKBACK_DAYS = 7
CAPACITY_COST_MIN_SAMPLES = 3
# the groups one grouped cost query may return before it reports truncation
CAPACITY_COST_GROUP_LIMIT = 5_000
# a purely advisory line a deployment may draw under rho to ask for attention
# - a tunable threshold, not a statement that capacity above it is safe
CAPACITY_RHO_ADVISORY_THRESHOLD = 0.7

################################################################
# django channels settings
################################################################
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{
                "host": REDIS_HOST,
                "port": REDIS_PORT,
                "socket_timeout": 6,
                # The auth of #1473: the channel layer talks to the same
                # instance as the broker and the cache, so it carries the same
                # credential. channels_redis passes this dict to redis's
                # ConnectionPool, where an empty password means no AUTH.
                "password": REDIS_PASSWORD,
            }],
            "capacity": 1500,  # default 100
            "expiry": 10,  # default 60
        },
    },
}

# Session settings and password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators
MIN_PASSWORD_LENGTH = 9
MIN_USERNAME_LENGTH = 5  # FUTURE: For production use another, more appropriate length!
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": MIN_PASSWORD_LENGTH,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = "/backend/static/"
STATIC_ROOT = "/var/www/mrmap/backend/"
STATIC_ROOT = STATIC_ROOT if check_path_access(
    STATIC_ROOT) else f"{BASE_DIR}/static"

WSGI_APPLICATION = "MrMap.wsgi.application"
ASGI_APPLICATION = "MrMap.asgi.application"

# Extends the number of GET/POST parameters
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# Threshold which indicates when to use multithreading instead of iterative approaches
MULTITHREADING_THRESHOLD = 2000

# Defines which User model implementation is used for authentication process
AUTH_USER_MODEL = "accounts.User"

# Defines how many seconds can pass until the session expires, default is 30 * 60
SESSION_COOKIE_AGE = 30 * 60

# Whether the session age will be refreshed on every request or only if data has been modified
SESSION_SAVE_EVERY_REQUEST = True

# Cookie policy of the browser session (#835, accepted decision Q8=B). The SPA
# authenticates with the session cookie ``api/auth/session`` opens; it is
# deliberately not readable by JavaScript (``HttpOnly``), so an injected script
# cannot copy it the way it could copy the knox token out of ``localStorage``.
# ``SameSite=Lax`` is enough here and is what the same-origin topology allows:
# nginx serves the SPA and proxies ``/api``, ``/csw`` and ``/ws`` on the very
# host and port the SPA is loaded from (``docker/nginx/mrmap.conf``), so every
# request which has to carry the credential is a same-site one anyway. A
# cross-site subresource which Lax blocks is therefore not a request which
# needs the session.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# The CSRF cookie is the one cookie the browser *must* hand to JavaScript: the
# SPA reads it and repeats its value in the ``X-CSRFToken`` header of every
# state-changing request, which is what DRF's ``SessionAuthentication`` demands
# for a request it authenticates through the session (see the contract in
# docs/source/administration/authentication.md). That value grants nothing on
# its own - without the session cookie it identifies no caller - so ``HttpOnly``
# stays off for it on purpose, and ``SameSite=Lax`` matches the session cookie.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Both cookies are only sent (and only stored) over TLS when the deployment is
# served over HTTPS. The default follows ``MRMAP_PRODUCTION`` because that is
# the deployment this repository ships behind nginx and TLS
# (``SECURE_PROXY_SSL_HEADER`` above reads the proxy's protocol); an http-only
# deployment must set ``DJANGO_COOKIE_SECURE=False``, or the browser refuses to
# store the session and no login ever sticks. Conversely an omitted flag would
# let the session cross the wire in clear text on a https deployment, which is
# why this is not left to the framework default of ``False``. Both cookies move
# together on purpose: a session stored over http without its CSRF partner, or
# the other way round, is not a working arrangement.


def _cookie_secure_from_env(environ, production: bool) -> bool:
    """Whether the session and CSRF cookies are TLS-only for one environment.

    The explicit ``DJANGO_COOKIE_SECURE`` wins over the deployment-mode default,
    so an http-only deployment can opt out and a https staging deployment which
    is not flagged as production can opt in.

    Blank is not a spelling of ``False``. It is what an unset variable looks like
    once anything has passed it through, and reading it as an answer would drop
    ``Secure`` from the session cookie of a production deployment on the strength
    of a value nobody wrote - the same reason ``_flag_from_env`` above treats it
    as "no decision" and the reason the pass-through in ``docker-compose.yml``
    uses the bare-name form. Only the two spellings of the block decide.
    """
    override = environ.get("DJANGO_COOKIE_SECURE")
    if override is not None and override.strip():
        return override.strip() == "True"
    return production


COOKIE_SECURE = _cookie_secure_from_env(os.environ, MRMAP_PRODUCTION)
SESSION_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SECURE = COOKIE_SECURE

################################################################
# FETCH HOST POLICY (#1474, SEC-16)
################################################################
# Where the backend may connect when it fetches a URL somebody else wrote: the service URL
# typed at registration, the operation URLs and onlineResource links of an upstream
# capabilities document, the metadata reference of a harvest and the redirect target of any
# of them. Both lists are comma separated CIDRs and are read per address by
# ``extras.ssrf``; a deny entry wins, an allow entry grants a range the default refuses, and
# the default refuses everything which is not a public address. Outside production the
# loopback and private ranges are granted as well, because the development stack and the unit
# tests are exactly those ranges. ``docs/source/administration/fetch-host-policy.md`` is the
# operator description, including how a deployment which hosts its services internally or is
# its own network opens the policy again.
MRMAP_FETCH_ALLOW_NETWORKS = os.environ.get("MRMAP_FETCH_ALLOW_NETWORKS", "")
MRMAP_FETCH_DENY_NETWORKS = os.environ.get("MRMAP_FETCH_DENY_NETWORKS", "")

################################################################
# DJANGO DEBUG TOOLBAR
################################################################
# Add the IP for which the toolbar should be shown
INTERNAL_IPS = ["127.0.0.1"]

# Defines xml namespaces used for xml parsing and creating.
# The plain http URIs are the normative namespace identifiers of the ISO, OGC, INSPIRE, GDI-DE and
# MapServer schemas. They are only registered with and compared literally by lxml, they are never
# resolved or requested over the network, so the insecure transport findings on them are false
# positives and are suppressed in place below.
XML_NAMESPACES = {
    "ogc": "http://www.opengis.net/ogc",
    "ows": "http://www.opengis.net/ows",
    "wfs": "http://www.opengis.net/wfs",
    "wms": "http://www.opengis.net/wms",
    "xlink": "http://www.w3.org/1999/xlink",
    "gml": "http://www.opengis.net/gml",
    "gmd": "http://www.isotc211.org/2005/gmd",  # NOSONAR normative ISO 19139 gmd namespace identifier, only parsed by lxml - not a network endpoint
    "gco": "http://www.isotc211.org/2005/gco",  # NOSONAR normative ISO 19103 gco namespace identifier, only parsed by lxml - not a network endpoint
    "srv": "http://www.isotc211.org/2005/srv",  # NOSONAR normative ISO 19139 srv namespace identifier, only parsed by lxml - not a network endpoint
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "ave": "http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/1.0",  # NOSONAR normative GDI-DE ALKIS Vereinfacht schema namespace identifier, only parsed by lxml - not a network endpoint
    "inspire_common": "http://inspire.ec.europa.eu/schemas/common/1.0",  # NOSONAR normative INSPIRE common schema namespace identifier, only parsed by lxml - not a network endpoint
    "inspire_com": "http://inspire.ec.europa.eu/schemas/common/1.0",  # NOSONAR normative INSPIRE common schema namespace identifier, only parsed by lxml - not a network endpoint
    "inspire_vs": "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0",  # NOSONAR normative INSPIRE view services schema namespace identifier, only parsed by lxml - not a network endpoint
    "inspire_ds": "http://inspire.ec.europa.eu/schemas/inspire_ds/1.0",  # NOSONAR normative INSPIRE data services schema namespace identifier, only parsed by lxml - not a network endpoint
    "inspire_dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0",  # NOSONAR normative INSPIRE download services schema namespace identifier, only parsed by lxml - not a network endpoint
    "epsg": "urn:x-ogp:spec:schema-xsd:EPSG:1.0:dataset",
    "ms": "http://mapserver.gis.umn.edu/mapserver",  # NOSONAR MapServer XML namespace identifier of the exported feature information, only parsed by lxml - not a network endpoint
    "se": "http://www.opengis.net/se",
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "sld": "http://www.opengis.net/sld",
    "fes": "http://www.opengis.net/fes/2.0",
    "csw": "http://www.opengis.net/cat/csw/2.0.2",
}

# Defines a generic template for xml element fetching without caring about the correct namespace
GENERIC_NAMESPACE_TEMPLATE = "*[local-name()='{}']"

################################################################
# Mapserver
################################################################
MAPSERVER_URL = os.environ.get("MAPSERVER_URL")
MAPSERVER_SECURITY_MASK_FILE_PATH = os.environ.get(
    "MAPSERVER_SECURITY_MASK_FILE_PATH"
)  # path on the machine which provides the mapserver service
MAPSERVER_SECURITY_MASK_TABLE = "registry_allowedwebmapserviceoperation"
MAPSERVER_SECURITY_MASK_GEOMETRY_COLUMN = "allowed_area"
MAPSERVER_SECURITY_MASK_KEY_COLUMN = "id"

DEFAULT_SRS = 4326
FONT_IMG_RATIO = 1 / 20  # Font to image ratio
ERROR_MASK_VAL = (
    # Indicates an error while creating the mask ("good" values are either 0 or 255)
    1
)
ERROR_MASK_TXT = (
    "Error during mask creation! \nCheck the configuration of security_mask.map!"
)


LOG_DIR = os.environ.get(
    "MRMAP_LOG_DIR", "/var/log/mrmap")


LOG_DIR = LOG_DIR if check_path_access(
    LOG_DIR) else f"{BASE_DIR}/logs"

LOG_FILE_MAX_SIZE = 1024 * 1024 * 20  # 20 MB
LOG_FILE_BACKUP_COUNT = 5

# create log dir if it does not exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


FILE_IMPORT_DIR = os.environ.get(
    "MRMAP_FILE_IMPORT_DIR", "/var/mrmap/import")

FILE_IMPORT_DIR = FILE_IMPORT_DIR if check_path_access(
    FILE_IMPORT_DIR) else f"{BASE_DIR}/import"

if not os.path.exists(FILE_IMPORT_DIR):
    os.makedirs(FILE_IMPORT_DIR)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rfc5424": {
            # see rfc5424 for syslog format: https://datatracker.ietf.org/doc/html/rfc5424
            # available fields: https://docs.python.org/3/library/logging.html#logrecord-attributes for a list of possible attributes
            "()": RFC5424Formatter,
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "DEBUG"
        },
    },
    "loggers": {
        ROOT_LOGGER_NAME: {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "disabled": False,
            "propagate": True,
        },
        "django": {
            "handlers": ["console"],
            "propagate": True,
        },
        "celery": {
            "handlers": ["console"],
            "propagate": True,
        },
        # "django.db.backends": {
        #    "handlers": ["console"],
        #    "level": "DEBUG",
        #    "propagate": False,
        # },
    },
}
# point the syslog handler at any RFC 5424 capable receiver; the default is the
# victoria-logs service of the compose stack
SYSLOG_HOST = os.getenv("MRMAP_SYSLOG_HOST", "victoria-logs")
SYSLOG_PORT = int(os.getenv("MRMAP_SYSLOG_PORT", "5514"))
try:
    """if syslog server is not reachable the application will not startup otherwise"""
    socket.getaddrinfo(SYSLOG_HOST, SYSLOG_PORT, proto=socket.IPPROTO_UDP)
    LOGGING["handlers"].update({
        "syslog": {
            "class": "logging.handlers.SysLogHandler",
            "formatter": "rfc5424",
            "facility": "user",
            "address": (SYSLOG_HOST, SYSLOG_PORT),
        },
    })
    LOGGING["loggers"][ROOT_LOGGER_NAME]["handlers"].append("syslog")
    LOGGING["loggers"]["django"]["handlers"].append("syslog")
    LOGGING["loggers"]["celery"]["handlers"].append("syslog")
    print("syslog logging handler configured.")
except socket.gaierror:
    print("syslog server is not reachable. skipping syslog handler setup.")

# the request duration in ms which is worth a "Slow Request Detected" record; the
# middleware of system/logging/middleware.py reads it while it builds itself
LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS = int(
    os.getenv("MRMAP_SLOW_REQUEST_THRESHOLD_MS", "400"))

# the records which the syslog handler formats and which carry detail beyond
# their code position leave a json dump with that detail below the media root,
# see system/logging/formatter.py; an ordinary record is answered by its syslog
# line alone (#1033). While the formatter wrote one per record, nothing used to
# take them back, so they grew with every log record (#888). The sweep which
# system/tasks.py names deletes them after this many days, aligned with the
# -retentionPeriod of the log store which keeps the syslog line pointing at them:
# a dropped dump loses the per request sql detail, nothing else. 0 keeps them
# until the cap below is reached
SLOW_REQUEST_DUMP_RETENTION_DAYS = int(
    os.getenv("MRMAP_SLOW_REQUEST_DUMP_RETENTION_DAYS", "14"))
# and keeps at most this many dumps, whichever bound is hit first; this bounds the
# directory itself, whose listing a chatty deployment pays for on every sweep. 0
# answers no cap, which leaves the age bound alone
SLOW_REQUEST_DUMP_MAX_FILES = int(
    os.getenv("MRMAP_SLOW_REQUEST_DUMP_MAX_FILES", "0"))

# the largest response body a monitoring probe keeps as an artifact of the
# execution; the size of a response is recorded either way, so the inspector
# can say why a body was not stored (#682)
MONITORING_PROBE_RESPONSE_MAX_SIZE = int(
    os.getenv("MRMAP_MONITORING_PROBE_RESPONSE_MAX_SIZE", "5242880"))
# how many days a stored probe response stays inspectable; the sweep which
# registry/tasks/monitoring.py names takes the bodies back after this many
# days while the result rows and their check answers stay, and the artifact
# endpoint refuses an older body as gone before the sweep reached it. 0 keeps
# every artifact until an operator removes it (#682)
MONITORING_PROBE_RESPONSE_RETENTION_DAYS = int(
    os.getenv("MRMAP_MONITORING_PROBE_RESPONSE_RETENTION_DAYS", "30"))

# how many days a decided background process stays part of the job history;
# the sweep which notify/tasks.py names deletes the processes which ended
# before this many days, together with their log entries, so the history of
# the job drawer stays bounded while the failures of the retention window
# remain discoverable (#1208). Processes which did not end yet are never
# touched. 0 keeps every process until an operator removes it
BACKGROUND_PROCESS_RETENTION_DAYS = int(
    os.getenv("MRMAP_BACKGROUND_PROCESS_RETENTION_DAYS", "90"))

# how many days a resolved operational incident stays inspectable; the sweep
# which notify/tasks.py names deletes the incidents which were resolved
# before this many days (#1319). The incidents which still stand are never
# touched - an active incident is the open problem itself - and the
# authoritative history of the reported operation is the job history of
# #1208 with its own retention. 0 keeps every resolved incident until an
# operator removes it
OPERATIONAL_INCIDENT_RETENTION_DAYS = int(
    os.getenv("MRMAP_OPERATIONAL_INCIDENT_RETENTION_DAYS", "90"))

# how many stored metadata files a single import task takes. The fan-out which
# writes harvested records to the database is one task per chunk instead of one per
# record (#859): a harvest of 70,000 records publishes ~280 broker messages, task
# round-trips and result writes instead of 70,000, and the import is limited by the
# database again. This is not the request step size of the catalogue
# (HarvestingJob.max_step_size), which is probed per service and stays untouched
HARVEST_IMPORT_BATCH_SIZE = int(
    os.getenv("MRMAP_HARVEST_IMPORT_BATCH_SIZE", "250"))
# How a draining import backlog reports its progress without writing the row of
# the background process once per file: a worker coalesces the files it has
# committed and reports them as one bulk increment after this many steps or
# once this many seconds have passed since its last report (#958). At the size
# of a real catalogue one UPDATE per file would turn the single row of the
# process into a row-lock hotspot behind every import transaction.
HARVEST_IMPORT_PROGRESS_STEPS = int(
    os.getenv("MRMAP_HARVEST_IMPORT_PROGRESS_STEPS", "200"))
HARVEST_IMPORT_PROGRESS_SECONDS = int(
    os.getenv("MRMAP_HARVEST_IMPORT_PROGRESS_SECONDS", "30"))
# The interval of the beat task which watches the harvests whose import backlog
# does not drain, in minutes (``registry.tasks.harvest.watch_import_backlogs``).
# The wait for an import chord is bounded by the retry budget this project hands
# celery, and when that budget runs out the chord's callback is dropped without
# any mrmap code being able to see it: the job stays open, its records unimported,
# and the only trace is a line in the worker log (#1038). The watchdog asks its
# question on this interval instead, and a backlog which stands still for one of
# them is reported on the job itself. The beat row of the task fires on the same
# value (see ``registry/apps.py``).
HARVEST_IMPORT_WATCH_INTERVAL_MINUTES = int(
    os.getenv("MRMAP_HARVEST_IMPORT_WATCH_INTERVAL_MINUTES", "5"))
# How many stored records the cleanup of an ended harvest (#1237) deletes per
# database batch: the rows of each batch go in a transaction of their own and
# the storage files follow after their commit, so neither one enormous
# transaction nor one transaction per file is what takes a 163k-record backlog
# back from an aborted job
HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE = int(
    os.getenv("MRMAP_HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE", "500"))
# How many stored records one fire of the cleanup task handles at most. The
# task which completes a big harvest is not allowed to become the next long
# runner of the deployment: what the bound leaves behind continues in the next
# fire of the same task (see registry/tasks/harvest.py, #1237)
HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN = int(
    os.getenv("MRMAP_HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN", "25000"))
# How many days a run must have been over before the historical scan of
# ``manage.py cleanup_temporary_harvest_files`` names it without being asked
# to. The terminal transitions schedule their cleanup immediately and the
# sweep and the recovery are race-safe anyway; the retention is the margin of
# an operator scanning the whole history by hand, and 0 scans everything
# already over (#1237)
HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS = int(
    os.getenv("MRMAP_HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS", "1"))
# How many days the records an ended run stored stay before the automatic
# cleanup of ``registry/tasks/harvest.py`` takes them back: the retention of
# this pile, which is what the sibling knobs of #888 and #682 answer for theirs.
# The records a run left behind are worth a retry while the run is fresh and
# nothing afterwards - on the rig of #1295 two registration waves of them filled
# 24.4 GB, because no boundary existed at all. 0 takes them back as soon as the
# run reached COMPLETED or ABORTED, which is what #1237 shipped with and what a
# deployment whose disk is the binding constraint wants; every day above 0 is
# the window in which the operator can still reschedule the import of a stored
# record of a run which completed before its rows and files go. Unlike the
# sibling knobs, a 0 here does not mean "keep forever": 0 is the minimum of the
# window, because an unbounded window over this pile is exactly the state #1295
# reports. This is not HARVEST_TEMP_FILE_CLEANUP_RETENTION_DAYS above, which is
# only the margin the operator's own scan of the whole history keeps to a run
# which ended moments ago (#1295)
HARVEST_TEMP_FILE_RETENTION_DAYS = int(
    os.getenv("MRMAP_HARVEST_TEMP_FILE_RETENTION_DAYS", "0"))

# How many hours an unfinished service-update job may stand undriven before the
# sweep of ``registry/tasks/update.py`` fails it (#1460). The guards of #1453
# redeliver a lost message, but a delivery which is gone for good - a broker
# recreated with the database kept, a purge, a discard - or a run whose retries
# died without the job deciding leaves it unfinished, and the constraint of one
# unfinished job per service then blocks every later update of that service.
# The sweep only fails unfinished jobs aged beyond this horizon; no legitimate
# update run takes so long, which is what makes the horizon the line that
# protects a job which still works. It fires hourly (see registry/apps.py).
# A horizon below one hour is raised to one: a busy queue is #1320's verdict,
# not this sweep's work
UPDATE_JOB_STALE_HORIZON_HOURS = int(
    os.getenv("MRMAP_UPDATE_JOB_STALE_HORIZON_HOURS", "24"))

# The activation gate of the metadata editor's record writes (#1241, opened
# by #1244). The create/update endpoints of the metadata records answer the
# default json:api CRUD contract; a committed write regenerates the ISO
# document served by the CSW through the publish seam of
# registry.mappers.publish, inside the same transaction as the fields
# (atomic publishing, decision 1 of the #1238 review). The round-trip and
# rejection tests of #1244's readiness clarification are what allowed this
# default to flip to True; an operator who sets it to False deliberately
# answers the record writes with 403 and keeps the editor read-only.
MRMAP_METADATA_EDITOR_WRITES_ENABLED = os.environ.get(
    "MRMAP_METADATA_EDITOR_WRITES_ENABLED", "True") == "True"


SIMPLE_HISTORY_HISTORY_ID_USE_UUID = True

JSON_API_FORMAT_FIELD_NAMES = "camelize"
JSON_API_FORMAT_RELATED_LINKS = "camelize"


def default_renderer_classes(production: bool):
    """Renderer classes of the REST API for one deployment mode.

    The browsable API renders an HTML page for any API response and is a
    development facility only. A production deployment must not answer it at
    all, so the browsable renderer is registered solely when the deployment is
    not production. This follows ``MRMAP_PRODUCTION`` and deliberately not
    ``DJANGO_DEBUG``: debug can be enabled by accident, which does not turn a
    deployment into a development one.

    Without the browsable renderer an explicitly HTML-only request is answered
    with the usual content negotiation rejection (406) instead of an API
    browser page, and requests without an ``Accept`` header or with
    ``Accept: */*`` receive the supported JSON:API representation.
    """
    renderers = ["extras.renderers.JSONRenderer"]
    if not production:
        renderers.insert(0, "extras.utils.BrowsableAPIRendererWithoutForms")
    return renderers


# Machine / API token lifetime (#835, accepted decision Q8=B). Since the browser
# authenticates with the Django session ``api/auth/session`` opens, the knox
# token this endpoint still issues is a *machine* credential only: scripts and
# CLI clients which authenticate with HTTP Basic and keep the answer. Its
# validity stays an explicit deployment decision instead of a package default:
# one working day, enforced server-side on every request against the
# ``AuthToken.expires`` row - not a client-side notion. ``AUTO_REFRESH`` stays
# off: a rolling extension would make the lifetime unpredictable and the token
# model has no refresh concept. Revocation is per token (#832). A dedicated
# machine-token policy - longer or unbounded lifetime, per-purpose scopes,
# admin-issued tokens - is the open decision documented in
# docs/source/administration/authentication.md and is deliberately not decided
# by this block; the browser session's own lifetime is ``SESSION_COOKIE_AGE``
# above and shares nothing with this one.
REST_KNOX = {
    "TOKEN_TTL": timedelta(hours=10),
    "AUTO_REFRESH": False,
    # Concurrency cap, not a lifetime (#1450): knox's stock default is None —
    # unlimited parallel tokens per user — so one credential seen by an
    # attacker could farm tokens without bound while a refusal to *issue* one
    # never leaks anything about the account. The login endpoint refuses with
    # 403 once the user already holds this many not-yet-expired rows; a logout
    # (or expiry) frees a slot, guessing at passwords cannot. Five covers the
    # scripts and CLI clients of one user across a working day; the browser
    # path of #835 logs in through ``api/auth/session`` and occupies no knox
    # row (see ``docs/source/administration/authentication.md``).
    "TOKEN_LIMIT_PER_USER": 5,
}

REST_FRAMEWORK = {
    "PAGE_SIZE": 10,
    "MAX_PAGE_SIZE": 100,
    "EXCEPTION_HANDLER": "rest_framework_json_api.exceptions.exception_handler",
    # The stack every view authenticates with unless it names its own. Basic
    # is deliberately NOT in it (#1450): Basic carries the account password,
    # and with this stack global, every endpoint of the API silently accepted
    # the password in place of the credential it documents - the machine token
    # of #835 exists exactly so that a caller does not hand out the password to
    # each request. The two endpoints the password is documented for,
    # ``api/auth/session`` and ``api/auth/login``, declare Basic on the view
    # now (``accounts/views/auth.py``), and they are the only ones.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "knox.auth.TokenAuthentication",
    ),
    # DRF 3.15 ships this empty, which throttles nothing: a scope only exists
    # once a rate is named here. The one scope is the login attempt budget of
    # #1450 - the POSTs of ``api/auth/session`` and ``api/auth/login``, the
    # two endpoints which read a password, counted per client address before
    # the credential is looked at (``accounts/throttling.py``).
    # ``30/min`` is sized from what the application itself does on one address:
    # the whole unit suite logs in about 25 times and the acceptance features
    # about 8, spread over minutes, and a browser or a script with a 10-hour
    # token re-logs in when a person types a password - nobody reaches 30 in a
    # minute by hand. A credential guessing tool loses over 99% of its rate.
    # A deployment whose machine clients all share one NAT address and log in
    # more often than this raises the number there.
    "DEFAULT_THROTTLE_RATES": {
        "login": "30/min",
    },
    # DRF's own default is an empty list, which asks nothing of anybody: a view
    # class naming no permission of its own answered writes to anonymous clients.
    # This is the floor such a view falls back to -- reading stays open, a write
    # needs an identity (#1444). Endpoints deciding access per object still name
    # their own classes, and the security proxy names none on purpose: OGC's XML
    # POST binding carries a GetFeature, which is a read, over HTTP POST.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "drf_spectacular_jsonapi.schemas.pagination.JsonApiPageNumberPagination",
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework_json_api.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_RENDERER_CLASSES": default_renderer_classes(MRMAP_PRODUCTION),

    "DEFAULT_METADATA_CLASS": "rest_framework_json_api.metadata.JSONAPIMetadata",
    "DEFAULT_SCHEMA_CLASS": "extras.schema.CustomOperationId",
    "DEFAULT_FILTER_BACKENDS": (
        "rest_framework_json_api.filters.QueryParameterValidationFilter",
        "rest_framework_json_api.filters.IncludedResourcesFilter",
        "rest_framework_json_api.filters.OrderingFilter",
        # "extras.filter_backend.CustomDjangoFilterBackend",
        "rest_framework_json_api.django_filters.backends.DjangoFilterBackend",
        # DRF's search, but asked of the search vector of a metadata record where a
        # view names one: the LIKE construction of the base is not indexable and,
        # joined over the keywords of a record, is the most expensive statement of a
        # searched list -- including the COUNT(*) of the pagination (#1029). See
        # registry/filters/search.py.
        "registry.filters.search.SearchVectorSearchFilter",
    ),
    "SEARCH_PARAM": "filter[search]",
    "TEST_REQUEST_RENDERER_CLASSES": (
        "rest_framework_json_api.renderers.JSONRenderer",
    ),
    "TEST_REQUEST_DEFAULT_FORMAT": "vnd.api+json",
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'MrMap json:api',
    'DESCRIPTION': 'spatial registry solution',
    'VERSION': VERSION,
    'SERVE_INCLUDE_SCHEMA': False,
    "COMPONENT_SPLIT_REQUEST": True,
    "PREPROCESSING_HOOKS": [
        "drf_spectacular_jsonapi.hooks.fix_nested_path_parameters"
    ],
    # the json:api view mixins' docstrings are implementation notes, not
    # endpoint documentation; see extras.schema.get_lib_doc_excludes
    "GET_LIB_DOC_EXCLUDES": "extras.schema.get_lib_doc_excludes",
    # the enum hook is spectacular's own default and must be named again
    # once the setting is overridden; the second hook moves the structured
    # enum labels (#1487) into the enum components the first hook extracts;
    # the last stamps the ISO 19139 element paths of the writable record
    # fields into the schema, read from the mapper configs (#1240)
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "extras.schema.inject_enum_labels",
        "registry.schema.inject_iso_paths",
    ],
}

if not MRMAP_PRODUCTION:
    # The browsable API renderer is already part of the development renderer
    # classes; see default_renderer_classes() above.
    INSTALLED_APPS.extend(
        [
            "behave_django",
        ]
    )


APPEND_SLASH = False

# Docker access is restricted to container list/inspect by the private API proxy.
SYSTEM_STATUS_DOCKER_URL = os.environ.get(
    "SYSTEM_STATUS_DOCKER_URL", "http://docker-api:2375")
SYSTEM_STATUS_DOCKER_PROJECT = os.environ.get(
    "SYSTEM_STATUS_DOCKER_PROJECT", "")
