"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 16.03.2020

"""
from django.contrib import admin
from monitoring.models import *
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.template.defaultfilters import escape

class HealthStateAdmin(admin.ModelAdmin):
    list_display = ('id', 'health_state_code', 'health_message', )


class MonitoringSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'check_time', 'timeout', 'periodic_task')


class MonitoringRunAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'start', 'end', 'duration', )


class MonitoringAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata_link', 'timestamp', 'duration', 'status_code', 'error_msg', 'available', 'monitored_uri', 'monitoring_run', )
    list_filter = ('monitoring_run', )

    def metadata_link(self, obj):
        return mark_safe('<a href="%s">%s</a>' % (reverse("admin:service_metadata_change", args=(obj.metadata.id,)), escape(obj.metadata)))

    metadata_link.allow_tags = True
    metadata_link.short_description = "metadata"


class MonitoringCapabilityAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'metadata', 'needs_update', 'diff')


admin.site.register(HealthState, HealthStateAdmin)
admin.site.register(MonitoringSetting, MonitoringSettingAdmin)
admin.site.register(Monitoring, MonitoringAdmin)
admin.site.register(MonitoringCapability, MonitoringCapabilityAdmin)

# Should not be visible for daily use
admin.site.register(MonitoringRun, MonitoringRunAdmin)
