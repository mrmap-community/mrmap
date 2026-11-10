from extras.viewsets import NestedModelViewSet
from notify.filters import BackgroundProcessFilterSet
from notify.models import BackgroundProcess, BackgroundProcessLog
from notify.permissions import CanChangeRelatedResource
from notify.serializers import (BackgroundProcessLogSerializer,
                                BackgroundProcessSerializer)
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class BackgroundProcessViewSetMixin(

):
    queryset = BackgroundProcess.objects.process_info()
    serializer_class = BackgroundProcessSerializer
    filterset_class = BackgroundProcessFilterSet
    permission_classes = [CanChangeRelatedResource]
    # the progress of process_info() is a plain annotation of the queryset, so
    # the overview can order its rows by the percentage it renders (#1035);
    # the state of #1207 is its other annotation and the revision its column
    ordering_fields = [
        "id",
        "date_created",
        "progress",
        "state",
        "revision",
    ]

    def get_queryset(self):
        """Answer only the processes which belong to resources the user may see.

        A process names its resource with a generic relation, so what the user is
        permitted to see has to be looked up per type of the related resource.
        Anonymous clients read this endpoint like every other read only endpoint
        of the api and a superuser sees every process, so neither of them needs
        the lookup.
        """
        queryset = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return queryset
        return BackgroundProcess.objects.visible_for_user(
            user, queryset=queryset)


class BackgroundProcessViewSet(
    BackgroundProcessViewSetMixin,
    ModelViewSet
):
    pass


class BackgroundProcessLogViewSetMixin(

):
    queryset = BackgroundProcessLog.objects.all()
    serializer_class = BackgroundProcessLogSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "log_type": ["exact", "icontains", "contains"],
        "description": ["exact", "icontains", "contains"],
        "date": ["exact", "icontains", "contains"],
    }
    ordering_fields = [
        "id",
    ]


class BackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class NestedBackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    NestedModelViewSet
):
    pass
