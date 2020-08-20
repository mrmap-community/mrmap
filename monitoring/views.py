from datetime import time

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.datetime_safe import datetime

from MrMap.decorator import check_permission
from monitoring.models import MonitoringSetting
from monitoring.tasks import run_monitoring
from service.helper.enums import MetadataEnum
from service.models import Metadata
from structure.models import Permission


@login_required
# @check_permission(Permission(can_run_monitoring=True))
def call_run_monitoring(request: HttpRequest, metadata_id):
    metadata = get_object_or_404(Metadata,
                                 ~Q(metadata_type=MetadataEnum.CATALOGUE.value),
                                 ~Q(metadata_type=MetadataEnum.DATASET.value),
                                 id=metadata_id, )

    mon_setting = MonitoringSetting(timeout=30, check_time=datetime.now())
    mon_setting.save()
    mon_setting.metadatas.add(metadata)
    mon_setting.save()

    try:
        run_monitoring(setting_id=mon_setting.id)
    except:
        pass



    return HttpResponseRedirect(reverse(request.GET.get('current-view') or reverse('home'),), status=303)
