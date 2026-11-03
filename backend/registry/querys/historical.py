from django.db.models import F, OuterRef, Q, Subquery


def with_prev_record_id(queryset):
    history_model = queryset.model

    previous_records = (
        history_model._default_manager
        .using(queryset.db)
        .filter(id=OuterRef("id"))
        .filter(
            Q(history_date__lt=OuterRef("history_date"))
            | Q(
                history_date=OuterRef("history_date"),
                history_id__lt=OuterRef("history_id"),
            )
        )
        .order_by("-history_date", "-history_id")
    )

    return queryset.annotate(
        prev_record_id=Subquery(
            previous_records.values("history_id")[:1]
        )
    )


def with_delta_size(queryset):
    """Alias the diff size which every audit row of the queryset carries.

    ``delta_size`` is written by the database when the row is inserted -- see
    the ``registry`` migration ``0025`` -- so this reads a column instead of
    comparing the row with its predecessor per row, which is what it used to be.
    The meaning is the one the filters and aggregations of the project were
    written against: NULL for a row without a predecessor, otherwise how many of
    the tracked, editable fields of the record differ in from that row, so that a
    save which changed nothing answers zero. Which fields those are is decided by
    the trigger, which compares the raw foreign key ids like ``diff_against()``
    does.

    A history which tracks many-to-many fields cannot be answered from the row
    alone, because such a change is not a column of it; the value the column
    would hold would silently leave that change out.
    """
    if queryset.model._history_m2m_fields:
        raise NotImplementedError(
            "Delta size does not support historical many-to-many fields."
        )

    return queryset.alias(_delta_size=F("delta_size"))
