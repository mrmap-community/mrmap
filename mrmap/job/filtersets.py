import django_filters
from job.models import Job, Task


class JobFilterSet(django_filters.FilterSet):

    class Meta:
        model = Job
        fields = {
            "id": ["in", ],
            "name": ["icontains", ],
        }


class TaskFilterSet(django_filters.FilterSet):

    class Meta:
        model = Task
        fields = {
            "id": ["in", ],
            "phase": ["icontains", ],
            "job": ["in", ],
        }
