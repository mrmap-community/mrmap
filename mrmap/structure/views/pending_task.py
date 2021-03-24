from django.urls import reverse_lazy
from main.views import SecuredDeleteView
from structure.models import PendingTask
from django.utils.translation import gettext as _


class PendingTaskDelete(SecuredDeleteView):
    model = PendingTask
    success_url = reverse_lazy('resource:pending-tasks')
    template_name = 'generic_views/generic_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _("Delete"),
            "msg": _("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context