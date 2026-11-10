import json

from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from drf_spectacular.utils import extend_schema_serializer
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from notify.enums import JobStateEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from rest_framework.fields import (CharField, DateTimeField, FloatField,
                                   SerializerMethodField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)

#: the display state of the Background Job Center which a stored status of a
#: process answers (#1207); the retrying state is derived in the serializer,
#: because it is a running process whose worker is between two attempts
STATUS_TO_STATE = {
    ProcessStatusEnum.PENDING: JobStateEnum.QUEUED.value,
    ProcessStatusEnum.RUNNING: JobStateEnum.RUNNING.value,
    ProcessStatusEnum.COMPLETED: JobStateEnum.COMPLETED.value,
    ProcessStatusEnum.FAILED: JobStateEnum.FAILED.value,
    ProcessStatusEnum.ABORTED: JobStateEnum.ABORTED.value,
}


class TaskResultSerializer(SystemInfoSerializerMixin, ModelSerializer):

    task_meta = SerializerMethodField()
    result = SerializerMethodField()

    url = HyperlinkedIdentityField(
        view_name='notify:taskresult-detail',
    )

    class Meta:

        model = TaskResult
        # meta field clashes with json:api meta field. We use alternate naming. See task_meta above.
        exclude = ("meta", )

    def get_task_meta(self, obj):
        return json.loads(obj.meta if obj.meta else '{}')

    def get_result(self, obj):
        return json.loads(obj.result if obj.result else '{}')


class BackgroundProcessLogSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='notify:backgroundprocesslog-detail',
    )

    class Meta:
        model = BackgroundProcessLog
        fields = "__all__"


@extend_schema_serializer(
    # the schema names this resource by its json:api type; without it the
    # component of an answer declared with the class rather than an instance
    # of this serializer is named after its metaclass (#1177)
    component_name="BackgroundProcess")
class BackgroundProcessSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='notify:backgroundprocess-detail',
    )

    date_created = DateTimeField(
        read_only=True,
        label=_("date created"),
        help_text=_("the datetime when the first thread was created"))
    done_at = DateTimeField(
        read_only=True,
        label=_("date at"),
        help_text=_("the datetime when the last thread was finished"))
    progress = FloatField(
        read_only=True,
        label=_("progress"),
        help_text=_("the current workflow progress from 0 to 100"))
    status = CharField(
        source="get_status_display",
        read_only=True,
        label=_("status"),
        help_text=_("the current workflow status."))
    related_resource = SerializerMethodField(
        label=_("related resource"),
        help_text=_(
            "the resource this process belongs to, addressed by its type and id"))
    state = SerializerMethodField(
        label=_("state"),
        help_text=_(
            "the logical state of the job for the Background Job Center"))
    is_retrying = SerializerMethodField(
        label=_("is retrying"),
        help_text=_("whether a task of this process is held in a retry"))
    error_summary = SerializerMethodField(
        label=_("error summary"),
        help_text=_(
            "the description of the last error which was logged about this process"))
    # logs = ResourceRelatedField(
    #    queryset=BackgroundProcessLog.objects,
    #    many=True,
    #    related_link_view_name='notify:backgroundprocess-logs-list',
    #    related_link_url_kwarg='parent_lookup_background_process'
    # )

    class Meta:
        model = BackgroundProcess
        exclude = ("threads", "celery_task_ids")

    # included_serializers = {
    #    'logs': BackgroundProcessLogSerializer,
    # }
    # }

    def get_related_resource(self, obj):
        # the type of the related resource is select_related by process_info(), so
        # this answers without an additional query - which matters here, because
        # the payload of every process of the background activity is built here.
        content_type = obj.related_resource_type
        if content_type is None or obj.related_id is None:
            return None
        model = content_type.model_class()
        if model is None:
            return None
        return {"type": model.__name__, "id": str(obj.related_id)}

    def get_state(self, obj):
        # the stored status is a number, its display name the word the overview
        # already answers with; the retrying state is no status of its own: the
        # work is still running, a worker is just between two attempts - so the
        # state is the status with the one decoration the drawer cannot derive
        # from the row alone. The getattr fallbacks keep an instance which was
        # not read through process_info() answerable.
        status = (
            ProcessStatusEnum.PENDING
            if obj.status is None
            else ProcessStatusEnum(obj.status)
        )
        if status == ProcessStatusEnum.RUNNING and getattr(obj, "is_retrying", False):
            return JobStateEnum.RETRYING.value
        return STATUS_TO_STATE[status]

    def get_is_retrying(self, obj):
        return bool(getattr(obj, "is_retrying", False))

    def get_error_summary(self, obj):
        summary = getattr(obj, "error_summary", None)
        return summary or None
