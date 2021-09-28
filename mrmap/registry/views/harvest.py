from django.urls import reverse_lazy

from jobs.models import Job
from extras.views import SecuredFormView
from registry.forms.harvest import StartHarvest
from registry.models import Service
from registry.tasks import harvest as harvest_tasks


class HarvestServiceFormView(SecuredFormView):
    model = Service
    action = "add"
    form_class = StartHarvest
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = 'Async task was created to create new resource.'
    # FIXME: wrong success_url

    #success_url = reverse_lazy('resource:pending-tasks')

    def form_valid(self, form):
        job_pk = harvest_tasks.harvest_service(
                        str(form.cleaned_data.get("service").pk),
                        **{"created_by_user_pk": self.request.user.pk,
                           "owned_by_org_pk": form.cleaned_data.get("service").owned_by_org_id})
        try:
            job = Job.objects.get(pk=job_pk)
            self.success_url = job.get_absolute_url()
        except Job.ObjectDoesNotExist:
            pass
        return super().form_valid(form=form)
