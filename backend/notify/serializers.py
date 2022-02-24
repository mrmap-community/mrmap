import json

from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from extras.serializers import StringRepresentationSerializer
from rest_framework.fields import (BooleanField, DateTimeField, IntegerField,
                                   SerializerMethodField)
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
    pending_threads = IntegerField(read_only=True)
    running_threads = IntegerField(read_only=True)
    successed_threads = IntegerField(read_only=True)
    failed_threads = IntegerField(read_only=True)
    all_threads = IntegerField(read_only=True)
    date_created = DateTimeField(read_only=True)
    is_done = BooleanField(read_only=True)
    has_failures = BooleanField(read_only=True)

    progress = SerializerMethodField(read_only=True)

    class Meta:
        model = BackgroundProcess
        fields = "__all__"

    def get_progress(self, instance):
        if instance.all_threads == 0:
            return 0
        aggregated_running_task_progress = 0.0
        running_thread: TaskResult
        for running_thread in instance.running_threads_list:
            meta_info = json.loads(
                running_thread.meta) if running_thread.meta else {}
            try:
                aggregated_running_task_progress += \
                    int(meta_info['current']) / int(meta_info['total'])
            except AttributeError:
                pass

        return (aggregated_running_task_progress + instance.successed_threads + instance.failed_threads - instance.pending_threads) * 100 / instance.all_threads
