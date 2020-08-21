from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse

from MrMap.decorator import check_permission
from monitoring.tasks import run_manual_monitoring
from service.helper.enums import MetadataEnum
from service.models import Metadata
from django.utils.translation import gettext_lazy as _

from structure.models import Permission


@login_required
@check_permission(Permission(can_run_monitoring=True))
def call_run_monitoring(request: HttpRequest, metadata_id):
    metadata = get_object_or_404(Metadata,
                                 ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                                 ~Q(metadata_type=MetadataEnum.DATASET.value),
                                 id=metadata_id, )

    run_manual_monitoring.delay(metadatas=[metadata_id, ])
    messages.info(request, _(f"Health check for {metadata} started."))

    return HttpResponseRedirect(reverse(request.GET.get('current-view') or reverse('home'),), status=303)
