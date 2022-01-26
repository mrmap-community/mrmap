from django.contrib.gis.db import models
from eulxml import xmlmap
from registry.models.metadata import DatasetMetadata
from registry.models.service import CatalougeService
from registry.xmlmapper.ogc.csw_get_record_response import \
    GetRecordsResponse as XmlGetRecordsResponse


def result_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/harvest_results/service_<id>/<filename>
    return "get_records_response/service_{0}/{1}".format(instance.service_id, filename)


class GetRecordsResponse(models.Model):
    service = models.ForeignKey(to=CatalougeService,
                                on_delete=models.CASCADE,
                                related_name="harvest_results",
                                related_query_name="harvest_result")
    result_file = models.FileField(upload_to=result_file_path,
                                   editable=False,
                                   max_length=1024)

    def parse(self) -> XmlGetRecordsResponse:
        return xmlmap.load_xmlobject_from_string(string=self.result_file.open().read(),
                                                 xmlclass=XmlGetRecordsResponse)

    def to_metadata_records(self):
        xml: XmlGetRecordsResponse = self.parse()

        for md_metadata in xml.records:
            DatasetMetadata.iso_metadata.create_from_parsed_metadata(
                parsed_metadata=md_metadata, related_object=self.service)
