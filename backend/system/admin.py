"""The admin view of the capacity telemetry rows (#1330).

The attempt samples are read where an administrator is allowed to see them
and edited nowhere: the rows are measurements, and a deployment that lets a
hand correct a duration has stopped measuring. The class is imported and
registered by the generic loop of ``MrMap/admin.py`` (the
``TemporaryMdMetadataFileAdmin`` pattern) and registers nothing on import, so
the autodiscovery of this module stays side-effect free.

There is also nothing here to leak even read-only: the model has no field
which could carry an argument, url, header or payload (the privacy boundary
of #1330), so the list and detail views show measurement columns only.
"""

from django.contrib import admin


class CeleryTaskAttemptAdmin(admin.ModelAdmin):
    list_display = ("task_name", "task_id", "attempt_no", "queue", "worker",
                    "periodic_name", "outcome", "started_at", "finished_at",
                    "active_seconds", "wait_seconds")
    list_filter = ("outcome", "queue")
    search_fields = ("task_name", "task_id", "periodic_name", "worker")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
