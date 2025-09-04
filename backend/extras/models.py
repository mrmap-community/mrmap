from django.db.models import Model
from django.db.models.expressions import F, Func
from django.db.models.fields import DateField, IntegerField
from django.db.models.fields.generated import GeneratedField


class HistoricalRecordMixin:

    def save(self, without_historical: bool = False, *args, **kwargs):
        if without_historical:
            self.skip_history_when_saving = True
        try:
            ret = super().save(*args, **kwargs)
        finally:
            if without_historical:
                del self.skip_history_when_saving
        return ret

# TODO: use get_current_timezone() to get the current timezone info for template purpose? #from django.utils.timezone import get_current_timezone


class AdditionalTimeFieldsHistoricalModel(Model):
    """
    Abstract model for history models to pre calculate time fields to use them for grouping by time periodes => statistical purpose
    """
    history_day = GeneratedField(
        expression=Func(
            F("history_date"),
            function="TIMEZONE",
            template="(%(function)s('EUROPE/BERLIN', %(expressions)s))::date",
            output_field=DateField(),
        ),
        output_field=DateField(),
        db_persist=True,
        db_index=True
    )
    # Week number (1–53, nach ISO-Standard in PostgreSQL)
    history_week = GeneratedField(
        expression=Func(
            F("history_date"),
            function="EXTRACT",
            template="EXTRACT(WEEK FROM (TIMEZONE('EUROPE/BERLIN', %(expressions)s)))",
            output_field=IntegerField(),
        ),
        output_field=IntegerField(),
        db_persist=True,
        db_index=True,
    )

    # Month (1–12)
    history_month = GeneratedField(
        expression=Func(
            F("history_date"),
            function="EXTRACT",
            template="EXTRACT(MONTH FROM (TIMEZONE('EUROPE/BERLIN', %(expressions)s)))",
            output_field=IntegerField(),
        ),
        output_field=IntegerField(),
        db_persist=True,
        db_index=True,
    )

    # Year (z. B. 2025)
    history_year = GeneratedField(
        expression=Func(
            F("history_date"),
            function="EXTRACT",
            template="EXTRACT(YEAR FROM (TIMEZONE('EUROPE/BERLIN', %(expressions)s)))",
            output_field=IntegerField(),
        ),
        output_field=IntegerField(),
        db_persist=True,
        db_index=True,
    )

    class Meta:
        abstract = True
