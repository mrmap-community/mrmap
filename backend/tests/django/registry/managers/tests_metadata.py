from pathlib import Path

from django.test import TestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.xml_mapper.iso_metadata.iso_metadata import WrappedIsoMetadata
from registry.models.metadata import DatasetMetadataRecord, Keyword


# TODO: #527
class IsoMetadataManagerTest(TestCase):

    def test_success(self):
        """Test that create manager function works correctly."""

        file_path = Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/iso_metadata/RBSN_FF.xml')).resolve().__str__()

        parsed_doc = load_xmlobject_from_file(
            filename=file_path, xmlclass=WrappedIsoMetadata)

        db_record = DatasetMetadataRecord.iso_metadata.update_or_create_from_parsed_metadata(
            parsed_metadata=parsed_doc.iso_metadata[0], origin_url="http://localhost")

        db_count = DatasetMetadataRecord.objects.count()
        self.assertEqual(1, db_count)

        db_keyword_count = Keyword.objects.count()
        self.assertEqual(6, db_keyword_count)
        self.assertEqual(6, db_keyword_count)
