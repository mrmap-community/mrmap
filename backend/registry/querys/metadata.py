from django.db import models
from django.db.models import Case, F, TextField, Value, When
from django.db.models.functions import Cast, Concat, Now
from django.utils.timezone import now
from registry.enums.metadata import MetadataOriginEnum


class TimeExtentQuerySet(models.QuerySet):

    def with_string_representation(self):
        """Annotate the display string which ``TimeExtent.__str__`` answers.

        The list endpoint offers ``sort=string_representation`` to the pickers
        which render exactly that string, so the annotation has to order rows
        the way the rendered value sorts: single values and intervals begin
        with their begin, a rolling extent with the time its window opens.
        The kind conditions are the ones of the model; importing them at
        module level would close the cycle model -> manager -> queryset ->
        model, so they are imported here (#1035).
        """
        from registry.models.metadata import IS_ROLLING, IS_SINGLE_VALUE

        return self.annotate(
            string_representation=Case(
                When(IS_SINGLE_VALUE,
                     then=Cast("begin", TextField())),
                When(IS_ROLLING,
                     then=Concat(
                         Cast(Now() - F("resolution"), TextField()),
                         Value(";"),
                         Cast(Now(), TextField()),
                         Value(";0"),
                         output_field=TextField())),
                default=Concat(
                    Cast("begin", TextField()),
                    Value(";"),
                    Cast("end", TextField()),
                    Value(";"),
                    Cast("resolution", TextField()),
                    output_field=TextField()),
                output_field=TextField()))

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


class MetadataContactQuerySet(models.QuerySet):

    def with_usage_count(self):
        """Annotate how many rows already reference each contact.

        The contact chooser of the metadata editor (#1246) shows this number
        next to every candidate: a curator who sees that a contact is carried
        by a dozen records picks it instead of creating another copy of the
        same address. Every FOREIGN KEY into this model is counted - records
        answer it as metadata, dataset or application contact, services and
        layers as service or metadata contact - summed into one number per
        row. The references are read from the model meta, so a reference
        added tomorrow is counted tomorrow: there is no list of tables here
        to forget.
        """
        from django.db.models import Count, IntegerField, OuterRef, Subquery
        from django.db.models.functions import Coalesce

        total = Value(0, output_field=IntegerField())
        for relation in self.model._meta.related_objects:
            # the reverse accessor of a FOREIGN KEY ONTO this model; its
            # `.field` is that key. A GenericForeignKey registers here too
            # but names no single column to match on - skip it.
            field = getattr(relation, "field", None)
            if field is None:  # pragma: no cover - no generic FKs today
                continue
            counted = (
                relation.related_model._default_manager
                .filter(**{field.name: OuterRef("pk")})
                .order_by()
                .values(field.name)
                .annotate(count=Count("pk"))
                .values("count")
            )
            total = total + Coalesce(
                Subquery(counted),
                Value(0, output_field=IntegerField()),
                output_field=IntegerField())
        return self.annotate(_usage_count=total)
