import decimal

from django.contrib import admin


def re_schedule_import_task(modeladmin, request, queryset):
    for obj in queryset:
        obj.re_schedule = True
        obj.save()


re_schedule_import_task.short_description = 'Reschedule import task'


class TemporaryMdMetadataFileAdmin(admin.ModelAdmin):
    # <-- Add the list action function here
    actions = [re_schedule_import_task, ]
