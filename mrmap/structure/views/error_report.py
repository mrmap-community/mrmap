from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django_celery_results.models import TaskResult
from extras.views import SecuredDetailView


@method_decorator(login_required, name='dispatch')
class ErrorReportDetailView(SecuredDetailView):
    model = TaskResult
    content_type = "text/plain"
    template_name = "structure/views/error-reports/error.txt"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{self.object.task_id}.txt"'
        return response