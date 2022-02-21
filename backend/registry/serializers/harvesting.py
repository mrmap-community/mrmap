from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from registry.models.harvest import HarvestingJob
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 UniqueTogetherValidator)


class HarvestingJobSerializer(
        StringRepresentationSerializer,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:harvestingjob-detail',
    )

    class Meta:
        model = HarvestingJob
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=HarvestingJob.objects.filter(done_at__isnull=True),
                fields=["service"],
                message=_(
                    "There is an existing harvesting job for this service.")
            )
        ]
