from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.generic import UpdateView
from django_bootstrap_swt.components import Alert
from django_bootstrap_swt.enums import AlertEnum


class AsyncUpdateView(UpdateView):
    template_name = 'generic_views/generic_update.html'
    action = ""
    action_url = ""
    alert_msg = ""
    async_task_func = None
    async_task_params = {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"action": self.action,
                        "action_url": self.action_url})
        return context

    def form_invalid(self, form):
        content = render_to_string(template_name=self.template_name,
                                   context=self.get_context_data(form=form),
                                   request=self.request)
        response = {
            "data": content
        }
        return JsonResponse(status=400, data=response)

    def form_valid(self, form):
        self.object.save()

        task = self.async_task_func.delay(object_id=self.object.id,
                                          additional_params=self.async_task_params)

        content = {
            "task": {
                "id": task.task_id,
                "alert": Alert(msg=self.alert_msg, alert_type=AlertEnum.SUCCESS).render()
            },
        }

        # cause this is a async task which can take longer we response with 'accept' status
        return JsonResponse(status=202, data=content)
