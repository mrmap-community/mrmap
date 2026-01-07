from django.db import models
from django.utils.timezone import now


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