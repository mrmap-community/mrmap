from registry.models.harvest import HarvestingJob
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class HarvestingJobSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:harvestingjob-detail',
    )

    class Meta:
        model = HarvestingJob
        fields = "__all__"
