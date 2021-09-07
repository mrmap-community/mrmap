from celery import states
from celery.worker.control import revoke
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import DetailView
from django_celery_results.models import TaskResult
from guardian.mixins import LoginRequiredMixin
from django.utils.translation import gettext as _


class PendingTaskDelete(LoginRequiredMixin, SuccessMessageMixin, DetailView):
    model = TaskResult
    # FIXME: wrong success_url
    # success_url = reverse_lazy('resource:pending-tasks')
    template_name = 'generic_views/base_extended/delete.html'
    success_message = _('Task canceled.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _("Delete"),
            "msg": _("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        revoke(task_id=self.object.task_id, state=states.REVOKED, terminate=True)
        return HttpResponseRedirect(self.success_url)
