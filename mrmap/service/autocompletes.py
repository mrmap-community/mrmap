from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from service.helper.enums import MetadataEnum
from service.models import Metadata


@method_decorator(login_required, name='dispatch')
class MetadataAutocomplete(autocomplete.Select2QuerySetView):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    model = Metadata
    search_fields = ['title', 'id']
    metadata_type = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.metadata_type:
            qs = qs.filter(metadata_type=self.metadata_type.value)
        return qs

    def get_result_label(self, result):
        """
            we need to override this function to show the id of the metadata object,
            so the user can differentiate the results where title is equal.
        """
        return '{} #{}'.format(result.title, result.id)


class MetadataServiceAutocomplete(MetadataAutocomplete):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    metadata_type = MetadataEnum.SERVICE


class MetadataDatasetAutocomplete(MetadataAutocomplete):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    metadata_type = MetadataEnum.DATASET


class MetadataLayerAutocomplete(MetadataAutocomplete):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    metadata_type = MetadataEnum.LAYER


class MetadataFeaturetypeAutocomplete(MetadataAutocomplete):
    """ Provides an autocomplete functionality for dataset metadata records

    """
    metadata_type = MetadataEnum.FEATURETYPE
