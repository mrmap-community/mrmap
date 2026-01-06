from django.db import models
from django.utils.timezone import now
from psycopg.types.range import Range



class TimeExtentQuerySet(models.QuerySet):

    def with_effective_timerange(self):
        """
        Annotates a dynamic 'effective_timerange':
        - Absolute → stored range
        - Rolling → [now - resolution, now]
        """
        current = now()
        annotated = []

        for obj in self:
            if obj.is_relative and obj.resolution:
                obj.effective_timerange = Range(
                    current - obj.resolution,
                    current,
                    '[]'
                )
            else:
                obj.effective_timerange = obj.timerange
            annotated.append(obj)

        return annotated

    def relevant_in(self, duration):
        """
        Filter objects whose effective range overlaps the last 'duration'.
        """
        current = now()

        return self.filter(
            models.Q(is_relative=True) |  # Rolling ranges
            models.Q(begin__lte=current, end__gte=current - duration)  # Absolute
        ).with_effective_timerange()