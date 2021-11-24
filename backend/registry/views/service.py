
from jobs.models import Job
from extras.views import SecuredFormView
from registry.tasks import service as service_tasks
from registry.forms.service import RegisterServiceForm
from registry.models import WebMapService


class RegisterServiceFormView(SecuredFormView):
    model = WebMapService
    action = "add"
    form_class = RegisterServiceForm
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = 'Async task was created to create new resource.'
    # FIXME: wrong success_url

    # success_url = reverse_lazy('resource:pending-tasks')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        cleaned_data.update({"registering_for_organization": cleaned_data["registering_for_organization"].pk})
        job_pk = service_tasks.register_service(
            form.cleaned_data,
            **{"created_by_user_pk": self.request.user.pk,
               "owned_by_org_pk": form.cleaned_data["registering_for_organization"]})
        try:
            job = Job.objects.get(pk=job_pk)
            self.success_url = job.get_absolute_url()
        except Job.ObjectDoesNotExist:
            pass
        return super().form_valid(form=form)
