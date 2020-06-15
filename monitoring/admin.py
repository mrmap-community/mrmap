"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 16.03.2020

"""
from django.contrib import admin

from monitoring.models import *


class MonitoringSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'check_time', 'timeout', 'periodic_task')


class MonitoringRunAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'start', 'end', 'duration')


class MonitoringAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata', 'timestamp', 'duration', 'status_code', 'error_msg', 'available', 'monitored_uri', 'monitoring_run')


class MonitoringCapabilityAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata', 'needs_update', 'diff')


admin.site.register(MonitoringSetting, MonitoringSettingAdmin)
admin.site.register(Monitoring, MonitoringAdmin)
admin.site.register(MonitoringCapability, MonitoringCapabilityAdmin)

# Should not be visible for daily use
#admin.site.register(MonitoringRun, MonitoringRunAdmin)
