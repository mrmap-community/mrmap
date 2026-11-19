# The dataset side of the coupling table gets the pair uniqueness its service
# side always had (#1483). A coupling is asserted by
# `MetadataRecord.add_metadata_relation` with `get_or_create`, and
# `select_for_update` locks a row which exists and nothing at all for a row
# which does not exist yet: two writers of one pair both saw no row and both
# wrote one. The dedupe runs first, because a deployment which already carries
# a repeated pair would otherwise be refused by the constraint this same
# migration adds.

from django.db import migrations, models
from django.db.models import Exists, OuterRef

#: the described elements a dataset record may be coupled to at all. The check
#: constraint `one_related_object_selected` of `MetadataRelation` - see
#: `registry/models/metadata_query.py` - allows a dataset metadata record beside
#: a layer and beside a feature type and nothing else, so these are also the
#: only two pair columns which need a constraint.
DATASET_ELEMENTS = ('layer', 'feature_type')


def _repeated_couplings(apps, element):
    """The couplings of one element which repeat a couple that stands already.

    A couple is identified the way `add_metadata_relation` identifies it: the
    element, the record and `is_internal`. `is_internal` belongs to the key by
    design - the imported evidence a capabilities document carried stays a row
    of its own beside a curator's internal coupling of the very same pair, see
    `MetadataRelation.publication_kind` - while the `origin` of a row does not
    split it, because the `get_or_create` does not ask it either.
    """
    MetadataRelation = apps.get_model('registry', 'MetadataRelation')
    earlier_of_the_same_couple = MetadataRelation.objects.filter(
        **{
            'pk__lt': OuterRef('pk'),
            'is_internal': OuterRef('is_internal'),
            f'{element}_id': OuterRef(f'{element}_id'),
            'dataset_metadata_id': OuterRef('dataset_metadata_id'),
        })
    return MetadataRelation.objects.filter(
        Exists(earlier_of_the_same_couple),
        **{
            f'{element}_id__isnull': False,
            'dataset_metadata_id__isnull': False,
        })


def drop_repeated_dataset_couplings(apps, schema_editor):
    """Leave the first row of every couple standing, drop its repetitions.

    The oldest row wins because that is the row every writer of the couple
    would have re-used: `get_or_create` returns the row it finds, and before
    this constraint existed, it found the first one written.
    """
    for element in DATASET_ELEMENTS:
        _repeated_couplings(apps, element).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0059_remove_catalogueservice_registry_ca_update__7b419c_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(
            drop_repeated_dataset_couplings,
            # the rows a repetition was are not restorable and nothing needs
            # them restorable: taking the constraint away is the whole reverse
            migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='metadatarelation',
            constraint=models.UniqueConstraint(
                fields=('is_internal', 'dataset_metadata', 'layer'),
                name='unique_dataset_metadata_representation_for_layer'),
        ),
        migrations.AddConstraint(
            model_name='metadatarelation',
            constraint=models.UniqueConstraint(
                fields=('is_internal', 'dataset_metadata', 'feature_type'),
                name='unique_dataset_metadata_representation_for_feature_type'),
        ),
    ]
