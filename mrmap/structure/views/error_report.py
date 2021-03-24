from main.views import SecuredDetailView
from structure.models import ErrorReport


class ErrorReportDetailView(SecuredDetailView):
    model = ErrorReport
    content_type = "text/plain"
    template_name = "structure/views/error-reports/error.txt"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{self.object.timestamp_now.strftime("%Y-%m-%dT%H:%M:%S")}.txt"'
        return response
