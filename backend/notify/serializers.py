from django_celery_results.models import TaskResult
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import CharField, ModelSerializer


class TaskResultSerializer(ModelSerializer):

    task_meta = CharField(source='meta')

    url = HyperlinkedIdentityField(
        view_name='notify:taskresult-detail',
    )

    class Meta:

        model = TaskResult
        # meta field clashes with json:api meta field. We use alternate naming. See task_meta above.
        exclude = ("meta", )
