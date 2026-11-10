from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_serializer
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from notify.enums import LogTypeEnum, OperationStateEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from rest_framework.fields import (CharField, DateTimeField, FloatField,
                                   IntegerField, SerializerMethodField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


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
        help_text=_("the datetime when this process was created"))
    done_at = DateTimeField(
        read_only=True,
        label=_("date at"),
        help_text=_("the datetime when this process reached its terminal state"))
    duration = FloatField(
        read_only=True,
        label=_("duration"),
        help_text=_(
            "the seconds between the creation and the decision of the "
            "process, empty while it still runs"))
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
            "the normalized state of the reported operation: queued while "
            "it waits for a worker, running while it works, "
            "running_indeterminate while it works without knowing its "
            "total number of steps, retrying while a retried task waits for "
            "its next attempt, action_required while a human decision is "
            "awaited, and the terminal failed, completed or aborted"))
    revision = IntegerField(
        read_only=True,
        label=_("revision"),
        help_text=_(
            "the number of the state report which every message about this "
            "process carries; a client which learns states out of order "
            "keeps the highest revision it has seen of each process"))
    error_summary = SerializerMethodField(
        label=_("error summary"),
        help_text=_(
            "what the last error of the reported operation told, or nothing "
            "where it never reported one"))
    retry_count = IntegerField(
        read_only=True,
        label=_("retry count"),
        help_text=_(
            "how many retries of its tasks the reported operation has "
            "reported since it was made"))
    retry_reason = CharField(
        read_only=True,
        label=_("retry reason"),
        help_text=_(
            "what the last reported retry of the operation failed on"))
    retry_scheduled_until = DateTimeField(
        read_only=True,
        label=_("retry scheduled until"),
        allow_null=True,
        help_text=_(
            "until when the next attempt of a retried task of the operation "
            "is due; while this window is open the operation reports itself "
            "as retrying"))
    # logs = ResourceRelatedField(
    #    queryset=BackgroundProcessLog.objects,
    #    many=True,
    #    related_link_view_name='notify:backgroundprocess-logs-list',
    #    related_link_url_kwarg='parent_lookup_background_process'
    # )

    class Meta:
        model = BackgroundProcess
        # `celery_task_ids` is the internal bookkeeping of which Celery tasks
        # belong to the process; it is written before a task is published and
        # read when the process is aborted - no client of the api reads it.
        # the flag behind the action_required state stays behind it: one
        # question, one answer in the contract (#1207). `threads` is gone with
        # #1223, so it is no longer named here.
        exclude = ("celery_task_ids", "action_required")

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
        # process_info() annotates the state over the stored fields and every
        # report payload is built from its instance; an instance rendered
        # straight after its creation - the answer of the asynchronous api -
        # carries no annotation and derives its state from the same fields
        state = getattr(obj, "state", None)
        if state is not None:
            return state
        return OperationStateEnum.derive(
            obj.status,
            action_required=obj.action_required,
            retry_scheduled_until=obj.retry_scheduled_until,
            total_steps=obj.total_steps)

    def get_error_summary(self, obj):
        # the annotation of process_info() answers the summary of every
        # rendered list row with one subquery; a single instance which was
        # not read through it answers the same question for itself
        if "error_summary" not in obj.__dict__:
            return obj.logs.filter(
                log_type=LogTypeEnum.ERROR,
            ).order_by("-date", "-id").values_list(
                "description", flat=True).first() or None
        return obj.error_summary or None
