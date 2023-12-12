from django.contrib import admin
from django.db.models.enums import TextChoices
from django.db.models.query import Q
from django.utils.translation import gettext_lazy as _


def re_schedule_import_task(modeladmin, request, queryset):
    for obj in queryset:
        obj.re_schedule = True
        obj.save()


re_schedule_import_task.short_description = 'Reschedule import task'


class ErrorChoices(TextChoices):
    UNKNOWN_HIERARCHY_LEVEL = "uhl", _("unknown HierachyLevel")
    EMPTY_DATASET_CONTACT = "edc", _("empty dataset contact")
    WRONG_DATESTAMP_FORMAT = "wdf", _("wrong datestamp format")
    UNKNOWN = "unknown", _("unknown")


UNKNOWN_HIERARCHY_LEVEL = Q(
    import_error__contains="file is neither server nor dataset record.")
EMPTY_DATASET_CONTACT = Q(
    import_error__contains='null value in column "dataset_contact_id"')
WRONG_DATESTAMP_FORMAT = Q(
    import_error__contains='File "/usr/local/lib/python3.11/_strptime.py", line 352, in _strptime')
UNKNOWN = UNKNOWN_HIERARCHY_LEVEL | EMPTY_DATASET_CONTACT | WRONG_DATESTAMP_FORMAT


class ErrorListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("kind of error")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "error"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return ErrorChoices.choices

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == "uhl":
            return queryset.filter(UNKNOWN_HIERARCHY_LEVEL)
        if self.value() == "edc":
            return queryset.filter(EMPTY_DATASET_CONTACT)
        if self.value() == "wdf":
            return queryset.filter(WRONG_DATESTAMP_FORMAT)
        if self.value() == "unknown":
            return queryset.exclude(UNKNOWN)


class TemporaryMdMetadataFileAdmin(admin.ModelAdmin):
    # <-- Add the list action function here
    actions = [re_schedule_import_task, ]
    list_display = ("pk", "error",)
    list_filter = [ErrorListFilter]

    def error(self, obj):
        if obj.import_error:
            if "file is neither server nor dataset record." in obj.import_error:
                return "unknown HierachyLevel"
            if 'null value in column "dataset_contact_id"' in obj.import_error:
                return "empty dataset contact"
            if 'File "/usr/local/lib/python3.11/_strptime.py", line 352, in _strptime' in obj.import_error:
                return "wrong datestamp format"
