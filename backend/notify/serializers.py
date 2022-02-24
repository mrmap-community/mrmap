import json

from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.serializers import StringRepresentationSerializer
from rest_framework.fields import SerializerMethodField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)

from notify.models import BackgroundProcess


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

    class Meta:
        model = BackgroundProcess
        fields = "__all__"
