"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 16.03.2020

"""
from django.contrib import admin

from monitoring.models import *


class HealthStateReasonAdmin(admin.ModelAdmin):
    list_display = ('id', 'health_state', 'monitoring_result', 'reason', 'health_state_code',)


class HealthStateAdmin(admin.ModelAdmin):
    list_display = ('id', 'health_state_code', 'health_message',)


class MonitoringSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'check_time', 'timeout', 'periodic_task')


class MonitoringRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'start', 'end', 'duration',)


class MonitoringAdmin(admin.ModelAdmin):
    list_display = (
    'id', 'timestamp', 'duration', 'status_code', 'error_msg', 'available', 'monitored_uri', 'monitoring_run',)
    list_filter = ('monitoring_run',)


class MonitoringCapabilityAdmin(admin.ModelAdmin):
    list_display = ('id', 'needs_update', 'diff')


admin.site.register(HealthStateReason, HealthStateReasonAdmin)
admin.site.register(HealthState, HealthStateAdmin)
admin.site.register(MonitoringSetting, MonitoringSettingAdmin)
admin.site.register(MonitoringResult, MonitoringAdmin)
admin.site.register(MonitoringResultDocument, MonitoringCapabilityAdmin)

# Should not be visible for daily use
admin.site.register(MonitoringRun, MonitoringRunAdmin)
