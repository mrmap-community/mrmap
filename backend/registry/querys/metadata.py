from django.db import models
from django.utils.timezone import now
from registry.enums.metadata import MetadataOriginEnum


class TimeExtentQuerySet(models.QuerySet):

    def relevant_in(self, duration):
        """
        Filter objects whose effective range overlaps the last 'duration'.
        """
        current = now()

        return self.filter(
            models.Q(is_relative=True) |  # Rolling ranges
            models.Q(begin__lte=current, end__gte=current - duration)  # Absolute
        )


class MetadataRelationQuerySet(models.QuerySet):
    """ Queryset which implements the coupling policy of MrMap.

        The cross table :class:`registry.models.metadata.MetadataRelation` is the only
        place where the coupling between a metadata record and a service resource is
        stored, but not every stored relation shall appear in the xml MrMap publishes.
        The policy is expressed by the provenance of the relation and splits all
        relations into three kinds, see
        :class:`registry.enums.metadata.MetadataRelationPublicationEnum`:

        * ``imported_evidence()``: ``is_internal=False``. The relation only documents a
          link which was found in a imported document. The link itself is stored in the
          related ``*RemoteMetadata`` model and is published through it.
        * ``publishable()``: ``is_internal=True`` and ``origin=EDITOR``. A curator
          created the relation in MrMap and it shall be published.
        * ``local_only()``: every other internal relation. MrMap knows the coupling, but
          no client shall see it.

        Note: Not every publishable relation can be published, the linked dataset
        metadata record must provide a resolvable origin url. See
        :attr:`registry.models.metadata.MetadataRelation.publication_url`.
    """

    def imported_evidence(self):
        """ Return all relations which only document an imported link. """
        return self.filter(is_internal=False)

    def local_only(self):
        """ Return all relations which are not intended for publication. """
        return self.filter(is_internal=True).exclude(
            origin=MetadataOriginEnum.EDITOR.value)

    def publishable(self):
        """ Return all curated relations which are intended for publication. """
        return self.filter(
            is_internal=True,
            origin=MetadataOriginEnum.EDITOR.value,
            dataset_metadata__isnull=False,
        )
