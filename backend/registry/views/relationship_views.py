from registry.models.harvest import HarvestingJob
from rest_framework_json_api.views import RelationshipView


class HarvestingJobRelationshipView(RelationshipView):
    queryset = HarvestingJob.objects
