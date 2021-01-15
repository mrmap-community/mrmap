from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import UpdateView, DetailView
from django.views.generic.edit import FormMixin
from django_bootstrap_swt.components import Alert
from django_bootstrap_swt.enums import AlertEnum, ButtonColorEnum

from MrMap.forms import ConfirmForm


class GenericUpdateView(UpdateView):
    template_name = 'generic_views/generic_update.html'
    action = ""
    action_url = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"action": self.action,
                        "action_url": self.action_url})
        return context


class AsyncUpdateView(GenericUpdateView):
    alert_msg = ""
    async_task_func = None
    async_task_params = {}

    def form_valid(self, form):
        self.object.save()

        task = self.async_task_func.delay(object_id=self.object.id,
                                          additional_params=self.async_task_params)

        content = {
            "data": {
                "id": task.task_id,
            },
            "alert": Alert(msg=self.alert_msg, alert_type=AlertEnum.SUCCESS).render()
        }

        # cause this is a async task which can take longer we response with 'accept' status
        return JsonResponse(status=202, data=content)


class ConfirmView(FormMixin, DetailView):
    template_name = 'generic_views/generic_confirm_form.html'
    success_url = reverse_lazy('home')
    form_class = ConfirmForm
    action = ""
    action_url = ""
    action_btn_color = ButtonColorEnum.PRIMARY

    # decorator or some other function could pass *args or **kwargs it to this function
    # so keep *args and **kwargs here to avoid from
    # TypeError: post() got an unexpected keyword argument 'pk' for example
    def post(self, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"action": self.action,
                        "action_url": self.action_url,
                        "action_btn_color": self.action_btn_color,})
        return context


class AsyncConfirmView(ConfirmView):
    alert_msg = ""
    async_task_func = None
    async_task_params = {}

    def form_valid(self, form):
        self.object.save()

        task = self.async_task_func.delay(object_id=self.object.id,
                                          additional_params=self.async_task_params)

        content = {
            "data": {
                "id": task.task_id,
            },
            "alert": Alert(msg=self.alert_msg, alert_type=AlertEnum.SUCCESS).render()
        }

        # cause this is a async task which can take longer we response with 'accept' status
        return JsonResponse(status=202, data=content)
