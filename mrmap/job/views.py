from django_filters.views import FilterView

from job.filtersets import JobFilterSet, TaskFilterSet
from job.models import Job, Task
from job.tables import JobTable, TaskTable
from main.views import SecuredListMixin


class JobListView(SecuredListMixin, FilterView):
    model = Job
    table_class = JobTable
    filterset_class = JobFilterSet
    template_name = 'job/views/job.html'


class TaskListView(SecuredListMixin, FilterView):
    model = Task
    table_class = TaskTable
    filterset_class = TaskFilterSet
    template_name = "job/views/task.html"
