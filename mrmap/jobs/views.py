from django_filters.views import FilterView

from jobs.filtersets import JobFilterSet, TaskFilterSet
from jobs.models import Job, Task
from jobs.tables import JobTable, TaskTable
from extras.views import SecuredListMixin


class JobListView(SecuredListMixin, FilterView):
    model = Job
    table_class = JobTable
    filterset_class = JobFilterSet
    template_name = 'jobs/views/jobs.html'


class TaskListView(SecuredListMixin, FilterView):
    model = Task
    table_class = TaskTable
    filterset_class = TaskFilterSet
    template_name = "jobs/views/task.html"
