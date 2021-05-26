from main.views import SecuredCreateView
from resourceNew import tasks
from resourceNew.forms import RegisterServiceForm
from resourceNew.models import Service
from django.urls import reverse_lazy
from django.conf import settings
from django.views.generic import FormView


class MapContextCreateView(FormView):
    model = Service
    form_class = RegisterServiceForm
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = 'Async task was created to create new resource.'
    success_url = reverse_lazy('resource:pending-tasks')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        cleaned_data.update({"registering_for_organization": cleaned_data["registering_for_organization"].pk})
        task = tasks.async_create_from_parsed_service.apply_async((form.cleaned_data, ),
                                                                   kwargs={'created_by_user_pk': self.request.user.pk,
                                                                           "owned_by_org_pk": form.cleaned_data["registering_for_organization"]},
                                                                   countdown=settings.CELERY_DEFAULT_COUNTDOWN)
        # todo filter pending tasks by task id
        return super().form_valid(form=form)
