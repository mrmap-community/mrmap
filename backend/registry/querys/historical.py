from django.db.models import (BooleanField, Case, F, Func, IntegerField,
                              OuterRef, Subquery, Value, When)


class IsDistinctFrom(Func):
    """PostgreSQL inequality that treats NULL as a comparable value."""

    template = "(%(expressions)s)"
    arg_joiner = " IS DISTINCT FROM "
    arity = 2
    output_field = BooleanField()


def with_delta_size(queryset):
    """Alias the diff size using the queryset's prev_record_id annotation.

    No predecessor produces NULL; an unchanged predecessor produces zero.
    Match diff_against()'s default editable, tracked fields and raw FK IDs.
    """
    history_model = queryset.model
    if history_model._history_m2m_fields:
        raise NotImplementedError(
            "Delta size does not support historical many-to-many fields."
        )

    size = Value(0, output_field=IntegerField())
    for field in history_model.tracked_fields:
        if field.editable:
            size += Case(
                When(
                    IsDistinctFrom(F(field.attname), OuterRef(field.attname)),
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )

    # Use the same predecessor as the page's bulk loading, independently of
    # filters on the outer queryset (including date ranges and change reasons).
    previous = (
        history_model._default_manager.using(queryset.db)
        .filter(history_id=OuterRef("prev_record_id"))
        .order_by()
        .annotate(_computed_delta_size=size)
    )
    return queryset.alias(
        _delta_size=Subquery(
            previous.values("_computed_delta_size")[:1],
            output_field=IntegerField(),
        )
    )
