import django_filters

from registry.models import ConformityCheckRun


class ConformityCheckRunFilterSet(django_filters.FilterSet):
    class Meta:
        model = ConformityCheckRun
        fields = {
            "id": ["in", ],
            "config__name": ["icontains", ],
            "passed": ["exact"],
        }
