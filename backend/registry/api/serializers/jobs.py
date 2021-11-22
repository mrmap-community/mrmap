from django_celery_results.models import TaskResult
from registry.models.jobs import RegisterOgcServiceJob
from rest_framework_json_api.serializers import ModelSerializer


class RegisterOgcServiceSerializer(ModelSerializer):

    class Meta:
        model = RegisterOgcServiceJob
        fields = "__all__"


class TaskResultSerializer(ModelSerializer):

    class Meta:
        model = TaskResult
        fields = [
            #"url", 
            "task_id", 
            "task_name", 
            "task_args", 
            "task_kwargs", 
            "status", 
            "worker", 
            "content_type", 
            "content_encoding", 
            "result",
            "date_created",
            "date_done",
            "traceback"]
        # exclude = ("meta", )  # meta field clashes with json:api meta field
