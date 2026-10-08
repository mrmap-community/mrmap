from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.fields import FloatField
from django.db.models.functions import Round
from notify.enums import ProcessStatusEnum


class BackgroundProcessManager(models.Manager):

    def process_info(self):
        qs = self.get_queryset()
        qs = qs.annotate(
            progress=Case(
                When(
                    Q(status=ProcessStatusEnum.COMPLETED),
                    then=Value(100.0)),
                When(
                    Q(total_steps__isnull=True),
                    then=Value(0.0)  # noqa
                ),
                # 1.0 factor is needed to force cast the F field to a decimal number...
                default=Case(
                    When(
                        total_steps__gt=0,
                        then=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precission=2),  # noqa

                    ),
                    default=0.0
                ),
                output_field=FloatField()
            )
        ).order_by('-date_created')
        return qs
