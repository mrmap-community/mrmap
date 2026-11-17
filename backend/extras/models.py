from django.conf import settings
from django.db.models import ForeignKey, SET_NULL
from django.db.models import Model
from django.db.models.expressions import F, Func
from django.db.models.fields import (DateField, DateTimeField, IntegerField,
                                     PositiveSmallIntegerField)
from django.db.models.fields.generated import GeneratedField
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


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

# FUTURE: use get_current_timezone() to get the current timezone info for template purpose? #from django.utils.timezone import get_current_timezone


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


class DeltaSizeHistoricalModel(Model):
    """Abstract model for history models which answer their own diff size.

    ``delta_size`` is how many of the tracked fields the row differs in from the
    row it precedes, written by the database when the row is inserted (see
    ``registry`` migration ``0025``). It is what the per-day statistics need to
    tell an update which changed something from a save which changed nothing --
    until now they answered it by comparing every row with its predecessor per
    request, which is why they could only be answered from a rebuild.

    Kept apart from ``AdditionalTimeFieldsHistoricalModel`` on purpose, although
    every model which uses this one also uses that one: the time fields are
    inherited by ``HarvestedMetadataRelation`` itself, which is not a history
    model but a resource of the api, and a column only the history needs must
    not appear in that resource.

    ``NULL`` means the row has no predecessor, which is not the same as ``0``:
    an audit row of a record which was created before history existed is not an
    update, it is the first thing known about that record.
    """
    delta_size = PositiveSmallIntegerField(
        null=True,
        editable=False,
        verbose_name=_("delta size"),
        help_text=_("how many tracked fields this record differs in from the "
                    "record which precedes it, empty without a predecessor"),
    )

    class Meta:
        abstract = True


class ChoiceModel(Model):
    """Abstract Modell für Choice-based Entities such as Language, Charset, etc."""
    value = PositiveSmallIntegerField(
        choices=[],
        primary_key=True,
        verbose_name=_("value")
    )

    class Meta:
        abstract = True
        ordering = ["value"]

    def __str__(self):
        return self.get_label()

    def get_label(self):
        choices = getattr(self, "CHOICES", [])
        return dict(choices).get(self.value, _("Unknown"))


class GrantMetadataMixin(Model):
    """Who wrote this object grant, and when (#740).

    Guardian keeps one row per object permission; a deployment which must
    answer "who granted what to whom" (#741) needs the decision next to the
    grant rather than in a second store which could disagree with it. The
    through-models of django-guardian are our own concrete subclasses
    (``accounts/models/guardian.py``, ``registry/models/guardian.py`` - the
    performance tables of #735), so the two columns live here and every
    concrete grant table gains them together.

    ``granted_by`` is the person the write is credited to. ``NULL`` is a
    meaningful answer, not a gap: the creation bootstrap of
    ``accounts.signals`` and the migrations of the role work write grants as
    a mechanical consequence of a creation, where no separate decision
    exists. Only paths which *are* a decision - a share of #740, an accepted
    ``PublishRequest`` - name one.

    ``created_at`` is written on every row, including bootstrap rows: when a
    grant appeared is a fact also of the grants nobody personally decided.

    One trap for the concrete classes: this mixin brings a ``Meta`` into the
    MRO, and Django takes the options of the FIRST base that has one - the
    guardian base's ``unique_together`` would silently drop out of the model
    state (and the next ``makemigrations`` would drop the constraint). Every
    concrete class therefore names its guardian base Meta explicitly:
    ``class Meta(UserObjectPermissionBase.Meta): pass``.
    """

    granted_by = ForeignKey(
        to=settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=SET_NULL,
        # the user-table accessor would collide with the through-model's own
        # "user" key (fields.E304); per-class names keep both readable
        related_name="%(class)s_granted_object_grants",
        verbose_name=_("granted by"),
        help_text=_(
            "the user who wrote this grant; empty for a grant the creation "
            "bootstrap or a migration wrote, where no person decided"),
    )
    created_at = DateTimeField(
        default=timezone.now,
        editable=False,
        verbose_name=_("created at"),
        help_text=_("when this grant row was written"),
    )

    class Meta:
        abstract = True
