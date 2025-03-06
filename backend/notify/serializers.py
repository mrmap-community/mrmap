import json

from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.serializers import StringRepresentationSerializer
from notify.models import BackgroundProcess, BackgroundProcessLog
from rest_framework.fields import (CharField, DateTimeField, FloatField,
                                   IntegerField, SerializerMethodField)
from rest_framework_json_api.relations import ResourceRelatedField
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


class BackgroundProcessLogSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='notify:backgroundprocesslog-detail',
    )

    class Meta:
        model = BackgroundProcessLog
        fields = "__all__"


class BackgroundProcessSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='notify:backgroundprocess-detail',
    )

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
    logs = ResourceRelatedField(
        queryset=BackgroundProcessLog.objects,
        many=True,
        related_link_view_name='notify:backgroundprocess-logs-list',
        related_link_url_kwarg='parent_lookup_background_process'
    )

    class Meta:
        model = BackgroundProcess
        fields = "__all__"

    included_serializers = {
        'logs': BackgroundProcessLogSerializer,
    }
