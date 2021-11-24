from django_celery_results.models import TaskResult
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import CharField


class TaskResultSerializer(ModelSerializer):

    task_meta = CharField(source='meta')

    url = HyperlinkedIdentityField(
        view_name='registry:taskresult-detail',
    )

    class Meta:
        
        model = TaskResult
        exclude = ("meta", )  # meta field clashes with json:api meta field. We use alternate naming. See task_meta above.
