"""Expressions which answer how long something measured took, as a number.

Durations are stored as intervals, and an interval cannot be divided by an
interval in Postgres. Anything which wants to compare a duration with a count -
how many records per minute a harvest managed (#692) - has to answer the length
of the interval in seconds first, which is what these expressions do.
"""
from django.db.models.expressions import Func
from django.db.models.fields import FloatField


class DurationSeconds(Func):
    """How many seconds a duration measures, answered as a number.

    `EPOCH` is the whole length of an interval in seconds, days and hours
    included - unlike `EXTRACT(SECOND FROM ...)`, which only names the seconds
    that are left after them.
    """

    function = "EXTRACT"
    template = "%(function)s(EPOCH FROM %(expressions)s)"
    output_field = FloatField()
