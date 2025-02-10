import json

from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.serializers import StringRepresentationSerializer
from notify.models import BackgroundProcess
from rest_framework.fields import (CharField, DateTimeField, FloatField,
                                   IntegerField, SerializerMethodField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class TaskResultSerializer(ModelSerializer):

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


class BackgroundProcessSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='notify:backgroundprocess-detail',
    )
    pending_threads_count = IntegerField(
        read_only=True,
        label=_("pending threads"),
        help_text=_("count of currently pending threads"))
    running_threads_count = IntegerField(
        read_only=True,
        label=_("running threads"),
        help_text=_("count of currently running threads"))
    successed_threads_count = IntegerField(
        read_only=True,
        label=_("successed threads"),
        help_text=_("count of currently successed threads"))
    failed_threads_count = IntegerField(
        read_only=True,
        label=_("failed threads"),
        help_text=_("count of currently failed threads"))
    date_created = DateTimeField(
        read_only=True,
        label=_("date created"),
        help_text=_("the datetime when the first thread was created"))
    progress = FloatField(
        read_only=True,
        label=_("progress"),
        help_text=_("the current progress aggregated from all threads from 0 to 100"))
    status = CharField(
        read_only=True,
        label=_("status"),
        help_text=_("the current status, aggregated from all threads."))

    class Meta:
        model = BackgroundProcess
        fields = "__all__"
