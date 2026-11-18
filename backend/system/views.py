import datetime
import os
import platform
import re

from django import __version__ as DJANGO_VERSION
from django.conf import settings
from django.db import ProgrammingError, connection
from django.http import Http404
from django.views.generic.base import View
from django.views.static import serve
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from MrMap import VERSION
from rest_framework.permissions import IsAdminUser
from rest_framework_json_api.views import ModelViewSet, generics
from system.capacity_snapshot import get_capacity_snapshot
from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR
from system.serializers import (CapacitySnapshotSerializer,
                                CrontabScheduleSerializer,
                                PeriodicTaskSerializer, SystemSerializer,
                                SystemStatusSerializer)
from system.status import get_status_snapshot


class CrontabScheduleViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `CrontabSchedule`

        create:
            Endpoint to register new `CrontabSchedule` object
        list:
            Retrieves all registered `CrontabSchedule` objects
        retrieve:
            Retrieve one specific `CrontabSchedule` by the given id
        partial_update:
            Endpoint to update some fields of a `CrontabSchedule`
        destroy:
            Endpoint to remove a registered `CrontabSchedule` from the system
    """
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer
    # the scheduler's tables decide what the fleet runs and when; like the
    # status and capacity views beside them this is admin only (#1445)
    permission_classes = [IsAdminUser]

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'minute': ['exact', 'icontains', 'contains'],
        'hour': ['exact', 'icontains', 'contains'],
        'day_of_month': ['exact', 'icontains', 'contains'],
        'month_of_year': ['exact', 'icontains', 'contains'],
        'day_of_week': ['exact', 'icontains', 'contains'],
        # 'timezone': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id",)
    ordering_fields = [
        "id",
        "minute",
        "hour",
        "day_of_month",
        "month_of_year",
        "day_of_week",
        # "timezone"
    ]


class PeriodicTaskViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `PeriodicTask`

        create:
            Endpoint to register new `PeriodicTask` object
        list:
            Retrieves all registered `PeriodicTask` objects
        retrieve:
            Retrieve one specific `PeriodicTask` by the given id
        partial_update:
            Endpoint to update some fields of a `PeriodicTask`
        destroy:
            Endpoint to remove a registered `PeriodicTask` from the system
    """
    queryset = PeriodicTask.objects.all()
    serializer_class = PeriodicTaskSerializer
    # writing a PeriodicTask schedules ANY registered Celery task with ANY
    # arguments - in-deployment job execution, so admin only (#1445)
    permission_classes = [IsAdminUser]

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'name': ['exact', 'icontains', 'contains'],
        'task': ['exact', 'icontains', 'contains'],
        # 'scheduling': ['exact', 'icontains', 'contains'],
        'args': ['exact', 'icontains', 'contains'],
        'kwargs': ['exact', 'icontains', 'contains'],
        'queue': ['exact', 'icontains', 'contains'],
        'enabled': ['exact'],
        # 'timezone': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id",)
    ordering_fields = [
        "id",
        "name",
        "task",
        "args",
        "kwargs",
        "queue",
        "enabled",
    ]


class SystemView(generics.RetrieveAPIView):
    """Release and platform versions, database name and size (#1445).

    The answer names the deployment's internals; since the scheduler views
    above became admin only this is the module's own standard - the status
    and capacity views have always answered admin only.
    """

    serializer_class = SystemSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):

        # System stats
        psql_version = db_name = db_size = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version(), current_database(), "
                    "pg_size_pretty(pg_database_size(current_database()))")
                psql_version, db_name, db_size = cursor.fetchone()
                psql_version = psql_version.split('(')[0].strip()
        except (ProgrammingError, IndexError):
            pass
        return {
            'id': VERSION,
            'mrmap_release': VERSION,
            'django_version': DJANGO_VERSION,
            'python_version': platform.python_version(),
            'postgresql_version': psql_version,
            'database_name': db_name,
            'database_size': db_size,
            'system_time': datetime.datetime.now(),
        }


class SystemStatusView(generics.RetrieveAPIView):
    serializer_class = SystemStatusSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        return get_status_snapshot()


class CapacitySnapshotView(generics.RetrieveAPIView):
    """The deployment capacity snapshot of #1326 - admin only, read only.

    ``GET`` answers the materialized snapshot: unique worker pools and
    their queue subscriptions, the integer depth and measured occupancy of
    every queue, the periodic demand of the horizon and ``rho`` only where
    both sides are comparable (always a ``periodic_only`` lower bound).
    The global workload and machine topology are exactly what #1326 says
    only a deployment administrator may see, so this answers 403 without a
    body section before any observation runs - a refusal cannot even pay
    for, or leak, a snapshot. Until the roles of #727 land,
    ``IsAdminUser`` is the deployment's admin answer, like the system
    status beside it.

    The answer is served from the cache (#1326: no 43k-schedule scan per
    request); see ``system/capacity_snapshot.py`` for what may and may not
    be claimed, and ``docs/source/development/capacity-snapshot.rst`` for
    the reading guide.
    """

    serializer_class = CapacitySnapshotSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "head", "options"]

    def get_object(self):
        return get_capacity_snapshot()


#: The subpaths of ``MEDIA_ROOT`` the media route never serves (#1447).
#:
#: Every entry holds files some writer of the deployment keeps for itself and
#: no HTTP consumer reads: the Fernet key files of the external service
#: authentications (``registry/models/security.py`` reads them through
#: ``FileField.path``, and nothing else ever opens one), the request and
#: response bodies the security proxy logged (their rows live in the database;
#: no serializer, view or screen of the application names their files), the
#: metadata documents a harvesting run staged (the cleanup command collects
#: them from the filesystem), and the dumps of the slow request logging
#: (#888, the first entry of this policy). Everything else below MEDIA_ROOT —
#: preview images and stored XML documents above all — stays public media:
#: the map clients and the download links of the frontend open it.
MEDIA_PRIVATE_SUBPATHS = (
    SLOW_REQUEST_DUMP_SUBDIR,
    "ext_auth_keys",
    "security_proxy/logs",
    "temporary_md_metadata_file",
)


class PrivateMediaNotFoundView(View):
    """Answer guarded media paths like unknown media files.

    The private subpaths of the media root carry credentials and logged
    payloads; deployments read them on the filesystem (#888, #1447). Accept
    the same verbs as ProtectedServeView so the refusal does not reveal
    guarded paths through a different response to an unsupported verb.
    """

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        raise Http404("Guarded media paths are not served.")


#: The url layer's own rule for the private subpaths, built from the policy
#: above so the two can never name different sets (MrMap/urls.py binds it
#: before the media route of either urlconf branch).
MEDIA_PRIVATE_URL_PATTERN = r"^media/(?:%s)/.+$" % "|".join(
    re.escape(subpath) for subpath in MEDIA_PRIVATE_SUBPATHS)


def _is_private_media(path, document_root):
    """Whether the resolved media path leads into a private subpath.

    Resolve both sides so dot segments, doubled separators and symlinks cannot
    expose guarded files through the media route. This is the view layer's
    own copy of the url rule above: the route is what refuses a request in a
    deployment, this check is what refuses one whose urlconf bound the media
    route without it, and a path reached through a symlink.
    """
    root = os.path.realpath(document_root or settings.MEDIA_ROOT)
    candidate = os.path.realpath(os.path.join(root, path))
    for subpath in MEDIA_PRIVATE_SUBPATHS:
        guarded = os.path.join(root, *subpath.split("/"))
        if candidate == guarded or candidate.startswith(guarded + os.sep):
            return True
    return False


class ProtectedServeView(View):
    """Serve uploaded media with read verbs, excluding the private subpaths."""

    http_method_names = ["get", "head"]

    def get(self, request, path, document_root=None, show_indexes=False):
        if _is_private_media(path, document_root):
            raise Http404("Guarded media paths are not served.")
        return serve(request, path, document_root, show_indexes)
