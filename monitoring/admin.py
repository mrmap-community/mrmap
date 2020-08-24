"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 16.03.2020

"""
from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.template.defaultfilters import escape
from monitoring.models import *


class HealthStateAdmin(admin.ModelAdmin):
    list_display = ('id', 'health_state_code', 'health_message', )


class MonitoringSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'check_time', 'timeout', 'periodic_task')


class MonitoringRunAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'start', 'end', 'duration', )


class MonitoringAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata', 'timestamp', 'duration', 'status_code', 'error_msg', 'available', 'monitored_uri', 'monitoring_run', 'health_state_link')

    def health_state_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:monitoring_healthstate_change", args=(obj.health_state.id,)), escape(f'{obj.health_state.health_state_code} - id: {obj.health_state.id}')))

    health_state_link.allow_tags = True
    health_state_link.short_description = "health_state"


class MonitoringCapabilityAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata', 'needs_update', 'diff')


admin.site.register(HealthState, HealthStateAdmin)
admin.site.register(MonitoringSetting, MonitoringSettingAdmin)
admin.site.register(Monitoring, MonitoringAdmin)
admin.site.register(MonitoringCapability, MonitoringCapabilityAdmin)

# Should not be visible for daily use
admin.site.register(MonitoringRun, MonitoringRunAdmin)
