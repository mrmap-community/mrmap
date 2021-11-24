from django.contrib.gis.db import models
from eulxml import xmlmap

from jobs.models import Job
from extras.models import CommonInfo
from registry.xmlmapper.ogc.csw_get_record_response import GetRecordsResponse


def result_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/harvest_results/service_<id>/job_<id>/<filename>
    return "harvest_results/service_{0}/job_{1}/{2}".format(instance.service_id, instance.job_id, filename)


class HarvestResult(CommonInfo):
    service = models.ForeignKey(to="CatalougeService",
                                on_delete=models.CASCADE,
                                related_name="harvest_results",
                                related_query_name="harvest_result")
    job = models.ForeignKey(to=Job,
                            on_delete=models.PROTECT,
                            related_name="harvest_results",
                            related_query_name="harvest_result")
    result_file = models.FileField(upload_to=result_file_path,
                                   editable=False,
                                   max_length=1024)

    class Meta:
        ordering = ['-created_at']

    def parse(self):
        result_xml = xmlmap.load_xmlobject_from_string(string=self.result_file.open().read(),
                                                       xmlclass=GetRecordsResponse)
        return result_xml
