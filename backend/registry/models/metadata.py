import logging
import re
from datetime import timedelta
from uuid import uuid4

from django.contrib.gis.db.models import MultiPolygonField
from django.contrib.gis.gdal.error import GDALException
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import BTreeIndex, GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import F, Q
from django.db.models.expressions import CombinedExpression
from django.db.models.fields.generated import GeneratedField
from django.db.transaction import atomic
from django.utils.timezone import now
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from epsg_cache.registry import Registry
from extras.managers import (ChoiceManager, DefaultHistoryManager,
                             UniqueConstraintDefaultValueManager)
from extras.models import (AdditionalTimeFieldsHistoricalModel, ChoiceModel,
                           DeltaSizeHistoricalModel)
from registry.enums.iso import (CategoryChoices, LanguageChoices,
                                MetadataCharsetChoices, UpdateFrequencyChoices)
from registry.enums.metadata import (DatasetFormatEnum, MetadataOriginEnum,
                                     MetadataRelationPublicationEnum,
                                     ReferenceSystemPrefixChoices,
                                     TimeExtentKind)
from registry.exceptions.service import NoContent
from registry.expressions.search import MetadataRecordSearchVector
from registry.managers.metadata import (ApplicationMetadataRecordManager,
                                        DatasetMetadataRecordManager,
                                        KeywordManager,
                                        MetadataRelationManager,
                                        ServiceMetadataRecordManager,
                                        TimeExtentManager)
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.document import MetadataDocumentModelMixin
from registry.models.metadata_query import VALID_RELATIONS
from requests import Request, Session
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError
from simple_history.models import HistoricalRecords
from urllib3 import Retry

CRS_Registry = Registry()


IS_SINGLE_VALUE = Q(
    Q(begin=F("end"))
)
IS_INTERVAL = Q(
    Q(end__gte=F("begin")) &
    Q(is_relative=False)
)

IS_ROLLING = Q(
    begin__isnull=True,
    end__isnull=True,
    is_relative=True,
    resolution__gt=timedelta(0),
)


class TimeExtent(models.Model):
    """Combined modell for singlevalue und intervalls.

    - Singlevalue: begin == end
    - Interval: begin < end

    Meta information:
    - Resolution: optional, None/0 = unendlich fein


    Rolling (window) temporal extent example:
    <gmd:EX_Extent id="timeperiodExtent">
        <gmd:temporalElement>
            <gmd:EX_TemporalExtent>
                <gmd:extent>
                    <gml:TimePeriod gml:id="d146058e755a1052958">
                        <gml:beginPosition indeterminatePosition="unknown"/>
                        <gml:endPosition indeterminatePosition="now"/>
                        <gml:duration>-P3D</gml:duration>
                    </gml:TimePeriod>
                </gmd:extent>
            </gmd:EX_TemporalExtent>
        </gmd:temporalElement>
    </gmd:EX_Extent>

    Note: The valid values for indeterminatePosition are “unknown”, “after”, “before”, and “now”

    """
    begin = models.DateTimeField(
        null=True,
        blank=False,
        verbose_name=_("begin"),
        help_text=_("the begin of the time period")
    )
    end = models.DateTimeField(
        null=True,
        blank=False,
        verbose_name=_("begin"),
        help_text=_("the end of the time period")
    )
    resolution = models.DurationField(
        blank=True,
        # do not allow Null. Otherwise the unique together constraint will not work as needed.
        # None != None from db pov
        default=timedelta(0),
        verbose_name=_("resolution"),
        help_text=_(
            "The resolution of the time extent. Null or 0 means infinite fine resolution.")
    )
    is_relative = models.BooleanField(default=False)

    objects = TimeExtentManager()

    class Meta:
        ordering = ["begin"]
        indexes = [
            # BTreeIndex Index for fast Overlap- and Contains-Requests
            BTreeIndex(fields=["begin", "end"]),
            models.Index(fields=["resolution"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(IS_SINGLE_VALUE | IS_INTERVAL | IS_ROLLING),
                name="kind_check",
            ),
            models.UniqueConstraint(fields=['begin', 'end', 'resolution', 'is_relative'],
                                    name='%(app_label)s_%(class)s_unique_timerange_resolution')
        ]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TimeExtent):
            return NotImplemented
        return (
            self.begin == other.begin
            and self.end == other.end
            and self.resolution == other.resolution
            and self.is_relative == other.is_relative
        )

    @property
    def kind(self):
        if self.begin and self.end and self.begin == self.end:
            return TimeExtentKind.SINGLE_VALUE
        elif self.begin and self.end and self.begin < self.end:
            return TimeExtentKind.INTERVAL
        elif (
            self.is_relative
            and self.begin is None
            and self.end is None
            and not self.has_infinite_resolution
        ):
            return TimeExtentKind.ROLLING
        return None

    @property
    def is_single_value(self):
        return self.kind == TimeExtentKind.SINGLE_VALUE

    @property
    def is_rolling(self):
        return self.kind == TimeExtentKind.ROLLING

    @property
    def has_infinite_resolution(self) -> bool:
        return self.resolution == timedelta(0)

    def __str__(self):
        if self.is_single_value:
            return f"{self.begin}"
        elif self.is_rolling:
            current = now()
            return f"{current - self.resolution};{current};0"
        else:
            res = self.resolution if self.resolution.total_seconds() != 0 else 0
            return f"{self.begin};{self.end};{res}"

    def iso_resolution(self) -> str:
        """
        Convert a timedelta to ISO 8601 duration (P[n]DT[n]H[n]M[n]S).
        Only supports days, hours, minutes, seconds.
        """
        if self.has_infinite_resolution:
            return "P0D"

        days = self.resolution.days
        seconds = self.resolution.seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        duration = "P"
        if days:
            duration += f"{days}D"
        if hours or minutes or seconds:
            duration += "T"
            if hours:
                duration += f"{hours}H"
            if minutes:
                duration += f"{minutes}M"
            if seconds:
                duration += f"{seconds}S"
        return duration

    def xml_value(self):
        """
        Serialize a single TimeExtent instance to string.
        - Single value: ISO timestamp
        - Interval: 'begin/end/resolution' (resolution as ISO 8601 duration)
        - Rolling: 'now - resolution;now;0' (dynamic)
        """
        if self.is_single_value:
            return self.begin.isoformat()

        elif self.is_rolling:
            current = now()
            start = current - self.resolution
            return f"{start.isoformat()};{current.isoformat()};0"

        else:  # Interval
            resolution_str = self.iso_resolution()
            return f"{self.begin.isoformat()}/{self.end.isoformat()}/{resolution_str}"


class MimeType(models.Model):
    mime_type = models.CharField(max_length=500,
                                 unique=True,
                                 db_index=True,
                                 verbose_name=_("mime type"),
                                 help_text=_("The Internet Media Type"))

    def __str__(self):
        return self.mime_type


class IsoCategory(ChoiceModel):
    CHOICES = CategoryChoices.choices
    value = models.PositiveSmallIntegerField(
        primary_key=True,
        choices=CHOICES,
        verbose_name=_("category"),
        help_text=_("the topic category of the dataset"))
    objects = ChoiceManager()


class Language(ChoiceModel):
    CHOICES = LanguageChoices.choices
    value = models.PositiveSmallIntegerField(
        primary_key=True,
        choices=CHOICES,
        verbose_name=_("language"),
        help_text=_("the language code as per ISO 639-2")
    )
    objects = ChoiceManager()


class Style(models.Model):
    layer = models.ForeignKey(to="registry.Layer",
                              on_delete=models.CASCADE,
                              editable=False,
                              verbose_name=_("related layer"),
                              help_text=_(
                                  "the layer for that this style is for."),
                              related_name="styles",
                              related_query_name="style")
    name = models.CharField(max_length=255,
                            editable=False,
                            verbose_name=_("name"),
                            help_text=_("The style's Name is used in the Map request STYLES parameter to lookup the "
                                        "style on server side."))
    title = models.CharField(max_length=255,
                             editable=False,
                             verbose_name=_("title"),
                             help_text=_("The Title is a human-readable string as an alternative for the name "
                                         "attribute."))

    def __str__(self):
        return f"{self.name}: {self.title}"


class LegendUrl(models.Model):
    legend_url = models.URLField(max_length=4096,
                                 editable=False,
                                 help_text=_("contains the location of an image of a map legend appropriate to the "
                                             "enclosing Style."))
    height = models.IntegerField(editable=False,
                                 help_text=_("the size of the image in pixels"))
    width = models.IntegerField(editable=False,
                                help_text=_("the size of the image in pixels"))
    mime_type = models.ForeignKey(to=MimeType,
                                  on_delete=models.RESTRICT,
                                  editable=False,
                                  related_name="legend_urls",
                                  related_query_name="legend_url",
                                  verbose_name=_("internet mime type"),
                                  help_text=_("the mime type of the remote legend url"))
    style = models.OneToOneField(to=Style,
                                 on_delete=models.CASCADE,
                                 editable=False,
                                 verbose_name=_("related style"),
                                 help_text=_(
                                     "the style entity which is linked to this legend url"),
                                 related_name="legend_url",
                                 related_query_name="legend_url")


class Licence(models.Model):
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255,
                                  unique=True)
    symbol_url = models.URLField(null=True)
    description = models.TextField()
    description_url = models.URLField(null=True)
    is_open_data = models.BooleanField(default=False)

    def __str__(self):
        return "{} ({})".format(self.identifier, self.name)


class ReferenceSystem(models.Model):
    # to inspect incorrect iso metadata records with wrong referencesystem setup, we allow empty default values.
    code = models.CharField(max_length=100,
                            default="")
    prefix = models.CharField(max_length=255,
                              choices=ReferenceSystemPrefixChoices.choices,
                              default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code', 'prefix'],
                                    name='%(app_label)s_%(class)s_unique_code_prefix')
        ]
        ordering = ["-code"]

    def __str__(self):
        return f"{self.prefix}:{self.code}" if self.prefix else self.code

    def __eq__(self, other) -> bool:
        if isinstance(other, ReferenceSystem):
            return self.code == other.code and self.prefix == other.prefix
        return NotImplemented

    @property
    def crs(self):
        if self.prefix == ReferenceSystemPrefixChoices.EPSG:
            try:
                return CRS_Registry.get(srid=self.code)
            except (ConnectionError, GDALException):
                pass

    @property
    def wkt(self):
        _crs = self.crs
        if _crs:
            return _crs.wkt

    @property
    def extent(self):
        _crs = self.crs
        if _crs:
            return _crs.extent

    @property
    def is_xy_order(self):
        _crs = self.crs
        if _crs:
            return _crs.is_xy_order

    @property
    def is_yx_order(self):
        _crs = self.crs
        if _crs:
            return _crs.is_yx_order


class MetadataContact(models.Model):
    name = models.CharField(max_length=256,
                            default='',
                            verbose_name=_("Name"),
                            help_text=_("The name of the organization"))
    person_name = models.CharField(max_length=200,
                                   default='',
                                   verbose_name=_("Contact person"))
    email = models.EmailField(max_length=100,
                              default='',
                              verbose_name=_('E-Mail'))
    phone = models.CharField(max_length=100,
                             default='',
                             verbose_name=_('Phone'))
    facsimile = models.CharField(max_length=100,
                                 default='',
                                 verbose_name=_("Facsimile"))
    city = models.CharField(max_length=100,
                            default='',
                            verbose_name=_("City"))
    postal_code = models.CharField(max_length=100,
                                   default='',
                                   verbose_name=_("Postal code"))
    address_type = models.CharField(max_length=100,
                                    default='',
                                    verbose_name=_("Address type"))
    address = models.CharField(max_length=100,
                               default='',
                               verbose_name=_("Address"))
    state_or_province = models.CharField(max_length=100,
                                         default='',
                                         verbose_name=_("State or province"))
    country = models.CharField(max_length=100,
                               default='',
                               verbose_name=_("Country"))

    objects = UniqueConstraintDefaultValueManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # we store only atomic contact records, identified by all fields
            # NOTE: Avoid nullable columns that are part of a unique constraint:
            # https://wladimirguerra.medium.com/only-one-null-in-unique-columns-234672fefc08
            models.UniqueConstraint(fields=['name',
                                            'person_name',
                                            'email',
                                            'phone',
                                            'facsimile',
                                            'city',
                                            'postal_code',
                                            'address_type',
                                            'address',
                                            'state_or_province',
                                            'country'],
                                    name='%(app_label)s_%(class)s_unique_together_metadata_contact')
        ]

    def __str__(self):
        if self.name:
            return self.name
        else:
            return ""


class Keyword(models.Model):
    # A keyword is free text: ISO 19115 gives gmd:keyword no length and catalogues
    # publish comma joined lists which are longer than any column width - the list
    # of the report which asked for this is 347 characters of perfectly good
    # metadata. A width on this column is therefore not a bound on bad input but a
    # reason for a whole metadata file to die: the insert of the keyword raised
    # StringDataRightTruncation, the import task judged that a record error and the
    # records of the file never entered the registry (#894).
    # The unique index over this column is the only real limit and it is not a
    # length: postgres stores a truncated key for a value it toasts, so the index
    # answers a keyword of any length (measured on this schema: 160,000 bytes
    # inserted into the unique index of a text column, block size 8 kB).
    keyword = models.TextField()

    objects = KeywordManager()

    def __str__(self):
        return self.keyword

    class Meta:
        ordering = ["keyword"]
        indexes = [
            models.Index(fields=["keyword"])
        ]
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_unique_keywords",
                fields=["keyword"]
            ),
            models.CheckConstraint(
                condition=Q(keyword__regex=r"\S") & Q(keyword__isnull=False),
                name="%(app_label)s_%(class)s_non_empty_keywords",
            )
        ]

    def natural_key(self):
        return (self.keyword,)


class RemoteMetadata(models.Model):
    """ Abstract model class to store linked iso metadata records while registration processing to fetch them after
        the service was registered. This helps us to parallelize the download processing with a celery group.

        To create the concrete metadata records the following workflow is necessary:
            1. fetch the remote content with fetch_remote_content(). After that the remote content was fetched.
            2. create the concrete metadata record (ServiceMetadataRecord | DatasetMetadataRecord) with create_metadata_instance()


    """
    # TODO: set link unique. IF we found one RemoteMetadata object with the same link, we can copy it and update the
    #  service fk to the service which was registered. Additional: we need to refactor the GenericForeignKey... We need
    #  then m2m relations to layers, featuretypes and services
    link = models.URLField(max_length=4094,
                           verbose_name=_("download link"),
                           help_text=_("the url where the metadata could be downloaded from."))
    remote_content = models.TextField(null=True,
                                      verbose_name=_("remote content"),
                                      help_text=_("the fetched content of the download url."))

    class Meta:
        abstract = True

    def fetch_remote_content(self, save=True):
        """ Return the fetched remote content and update the content if save is True """

        session = Session()
        retries = Retry(
            total=3,
            backoff_factor=0.1
        )
        session.mount(self.link, HTTPAdapter(max_retries=retries))
        # FIXME: Re add authentication
        request = Request(method="GET",
                          url=self.link,
                          # auth=auth,
                          )

        response = session.send(request.prepare())

        if response.status_code == 200 and len(response.text) > 0:
            self.remote_content = response.text
            if save:
                self.save()
            return self.remote_content
        else:
            raise NoContent(
                f"Can't fetch content from remote for RemoteMetadata with id {self.pk}")

    def create_metadata_instance(self, **kwargs):
        """ Return the created metadata record, based on the content_type of the described element. """

        mappers = MDMetadataXmlMapper.from_xml(self.remote_content.encode())
        data = mappers[0].xml_to_django()
        parsed_instance = data[0]
        handler = PersistenceHandler(
            mapper=mappers[0],
            defaults={
                "dataset": {
                    "origin": MetadataOriginEnum.CAPABILITIES.value,
                    "origin_url": self.link
                }
            }
        )
        created_instances = handler.persist_all()
        # search by unique file_identifier to get the created record.
        created_instance = next(
            (
                v for k, v in created_instances.get(parsed_instance.__class__, {}).items()
                if parsed_instance.file_identifier in k
            ),
            None
        )

        if not created_instance:
            logging.warning(
                f"can not create record with fileIdentifier: {parsed_instance.file_identifier}")
            return

        created_instance.add_metadata_relation(
            related_object=self.describes)
        return created_instance


class WebMapServiceRemoteMetadata(RemoteMetadata):
    describes = models.ForeignKey(to="registry.WebMapService",
                                  on_delete=models.CASCADE,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("web map service"),
                                  help_text=_("the service where this remote metadata is related to. This remote metadata"
                                              " was found in the GetCapabilites document of the related service."))


class LayerRemoteMetadata(RemoteMetadata):
    describes = models.ForeignKey(to="registry.Layer",
                                  on_delete=models.CASCADE,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("layer"),
                                  help_text=_("the service where this remote metadata is related to. This remote metadata"
                                              " was found in the GetCapabilites document of the related service."))


class WebFeatureServiceRemoteMetadata(RemoteMetadata):
    describes = models.ForeignKey(to="registry.WebFeatureService",
                                  on_delete=models.CASCADE,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("web feature service"),
                                  help_text=_("the service where this remote metadata is related to. This remote metadata"
                                              " was found in the GetCapabilites document of the related service."))


class FeatureTypeRemoteMetadata(RemoteMetadata):
    describes = models.ForeignKey(to="registry.FeatureType",
                                  on_delete=models.CASCADE,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("featuretype"),
                                  help_text=_("the service where this remote metadata is related to. This remote metadata"
                                              " was found in the GetCapabilites document of the related service."))


class CatalogueServiceRemoteMetadata(RemoteMetadata):
    describes = models.ForeignKey(to="registry.CatalogueService",
                                  on_delete=models.CASCADE,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("catalogue service"),
                                  help_text=_("the service where this remote metadata is related to. This remote metadata"
                                              " was found in the GetCapabilites document of the related service."))


class MetadataTermsOfUse(models.Model):
    """ Abstract model class to define some fields which describes the terms of use for an metadata

    """
    access_constraints = models.TextField(null=True,
                                          blank=True,
                                          verbose_name=_("access constraints"),
                                          help_text=_("access constraints for the given resource."))
    fees = models.TextField(null=True,
                            blank=True,
                            verbose_name=_("fees"),
                            help_text=_("Costs and of terms of use for the given resource."))
    use_limitation = models.TextField(null=True,
                                      blank=True)
    license_source_note = models.TextField(null=True,
                                           blank=True, )
    licence = models.ForeignKey(to=Licence,
                                on_delete=models.RESTRICT,
                                blank=True,
                                null=True)

    class Meta:
        abstract = True


class AbstractMetadata(MetadataDocumentModelMixin):
    """ Abstract model class to define general fields for all concrete metadata models. """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    date_stamp = models.DateTimeField(verbose_name=_('date stamp'),
                                      help_text=_('date that the metadata was created. If this is a metadata record '
                                                  'which is parsed from remote iso metadata, the date stamp of the '
                                                  'remote iso metadata will be used.'),
                                      # Do not use this setting.
                                      # From django docs: Automatically set the field to now when the object is first created.
                                      # Useful for creation of timestamps. Note that the current date is always used;
                                      # it’s not just a default value that you can override.
                                      # So even if you set a value for this field when creating the object, it will be ignored.
                                      # If you want to be able to modify this field, set the following instead of auto_now_add=True:
                                      # auto_now_add=True,
                                      default=now,
                                      editable=False,
                                      db_index=True)
    file_identifier = models.CharField(max_length=1000,
                                       editable=False,
                                       default=uuid4,
                                       db_index=True,
                                       verbose_name=_("file identifier"),
                                       help_text=_("the parsed file identifier from the iso metadata xml "
                                                   "(gmd:fileIdentifier) OR for example if it is a layer/featuretype"
                                                   "the uuid of the described layer/featuretype shall be used to "
                                                   "identify the generated iso metadata xml."))
    origin = models.PositiveSmallIntegerField(choices=MetadataOriginEnum.choices,
                                              null=True,
                                              editable=False,
                                              verbose_name=_("origin"),
                                              help_text=_("Where the metadata record comes from."))
    origin_url = models.URLField(max_length=4096,
                                 null=True,
                                 blank=True,
                                 editable=False,
                                 verbose_name=_("origin url"),
                                 help_text=_("the url of the document where the information of this metadata record "
                                             "comes from"))
    title = models.CharField(max_length=1000,
                             verbose_name=_("title"),
                             help_text=_(
                                 "a short descriptive title for this metadata"),
                             default="")
    abstract = models.TextField(verbose_name=_("abstract"),
                                help_text=_(
                                    "brief summary of the content of this metadata."),
                                blank=True,
                                default="")
    is_broken = models.BooleanField(default=False,
                                    editable=False,
                                    verbose_name=_("is broken"),
                                    help_text=_("TODO"))
    is_customized = models.BooleanField(default=False,
                                        editable=False,
                                        verbose_name=_("is customized"),
                                        help_text=_("If the metadata record is customized, this flag is True"))
    insufficient_quality = models.TextField(default="",
                                            blank=True,
                                            editable=False,
                                            help_text=_("TODO"))
    is_searchable = models.BooleanField(default=False,
                                        verbose_name=_("is searchable"),
                                        help_text=_("only searchable metadata will be returned from the search api"))
    hits = models.PositiveIntegerField(default=0,
                                       verbose_name=_("hits"),
                                       help_text=_(
                                           "how many times this metadata was requested by a client"),
                                       editable=False, )
    keywords = models.ManyToManyField(to=Keyword,
                                      blank=True,
                                      related_name="%(class)s_metadata",
                                      related_query_name="%(class)s_metadata",
                                      verbose_name=_("keywords"),
                                      help_text=_("all keywords which are related to the content of this metadata."))

    languages = models.ManyToManyField(to=Language,
                                       blank=True,
                                       related_name="%(class)s_metadata",
                                       related_query_name="%(class)s_metadata",
                                       verbose_name=_("languages"),
                                       help_text=_("languages used for documenting metadata"))

    class Meta:
        abstract = True
        ordering = ["title"]
        indexes = [
            models.Index(fields=["title", "file_identifier"]),
        ]
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_unique_file_identifier",
                fields=["file_identifier"]
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.pk})"

    def save(self, *args, mark_customized: bool = True, **kwargs):
        """Save the record and say with `mark_customized` who wrote it.

        An update of a record is a customization of it, which is what the flag
        answers to the editor. A write of the harvesting process is not one: the
        record came from the catalogue as the catalogue has it, and flagging every
        re-harvest as customized tells that somebody edited it (#858). Those
        writes pass `mark_customized=False`.
        """
        if not self._state.adding and mark_customized:
            self.is_customized = True

        return super().save(*args, **kwargs)

    # The threshold of the keyword list rule (#919), see
    # keyword_publishes_several_values().
    #
    # Measured before it was chosen, as the issue demands: the issue's two
    # queries ran over the keyword corpus this repository carries - the
    # fixture keyword tables plus every gmd:keyword of the real-world ISO
    # 19139 documents below tests/django/test_data (DWD, GDI-DE, GDI-BW),
    # 417 distinct keywords in 29 records. 17 of them carry a comma and all
    # of them are list-shaped for the regex of the issue; 16 are legitimate
    # single values - German appositions ("Heimerziehung, in einer
    # Einrichtung") and decimal commas ("Horizontale Auflösung von 0,0625
    # Grad") - and the longest of them is 50 characters. The reported defect
    # shape (the ten plan names of the GDI-BW record, 315 characters in the
    # corpus document) is flagged by every threshold from 50 on; the 9 single
    # valued keywords longer than 100 characters carry no delimiter and stay
    # unflagged at every threshold,
    # which is the proof that the rule does not become a length rule in
    # disguise. 100 keeps a factor of two to the longest legitimate comma
    # keyword and flags 1 of 29 corpus records - a signal, not the wall of
    # chips the issue warns about.
    KEYWORD_LIST_THRESHOLD = 100

    @classmethod
    def keyword_publishes_several_values(cls, keyword):
        """Whether one gmd:keyword element carries a list of values (#919).

        A catalogue which publishes ten values in one element should have
        published ten elements: "Keyword value" is 1..*. The comma alone is
        not the signal - a legitimate keyword can carry one as an
        apposition or as a decimal separator - so the rule is the number of
        delimiter separated parts and the length of the element together.
        What the rule deliberately does not do: judge the text. The blank
        rule of parse_keyword stays the only text judgement on a keyword,
        the keyword is never split, rejected or rewritten, and this is no
        length rule: it is about granularity, so a part count of one keeps
        every long keyword unflagged.
        """
        parts = [p.strip() for p in re.split(r"[,;]", keyword) if p.strip()]
        return len(parts) > 1 and len(keyword) > cls.KEYWORD_LIST_THRESHOLD

    def quality_findings(self, keywords=None):
        """The machine statements which the quality rules make about this record.

        One rule for now (#919), so one finding per offending keyword
        element. Each finding is a translated sentence naming the keyword it
        reports - the field renders verbatim as chip, tooltip and detail
        text in de and en, so it is translated at write time, not at read
        time. The keyword of a finding is excerpted because a keyword is as
        long as its catalogue says (#894) and a tooltip must stay readable.

        Args:
            keywords: the keyword strings to judge, the already mapped ones
                from the import hot path; None asks the stored keywords of
                a saved record instead.
        """
        if keywords is None:
            keywords = self.keywords.values_list("keyword", flat=True)
        findings = []
        for keyword in keywords:
            if self.keyword_publishes_several_values(keyword):
                parts = [p.strip() for p in re.split(r"[,;]", keyword) if p.strip()]
                excerpt = keyword if len(keyword) <= 120 else keyword[:120] + "…"
                findings.append(gettext(
                    "The keyword '%(keyword)s' publishes %(count)d values in one "
                    "gmd:keyword element; the catalogue should publish one "
                    "gmd:keyword element per value.") % {
                        "keyword": excerpt, "count": len(parts)})
        return findings

    def refresh_quality_indicators(self, keywords=None):
        """Recompute the quality indicator of #600 and answer what changed.

        The field is one slot for the agreed string of all findings, so a
        later rule joins its sentence in instead of overwriting this one.
        `is_broken` stays untouched: a comma joined keyword list is a
        quality problem, not broken metadata, and the read side of #600
        renders the two indicators apart (the quality chip warns, the
        broken chip reports damage).

        The method writes nothing. The import hands the already mapped
        keywords in and lets the answer ride the one write which the record
        costs anyway (#858); a caller which asks a saved record without
        keywords reads them from the relation.

        Args:
            keywords: the keyword strings to judge; None asks the stored
                keywords of a saved record.

        Returns:
            bool: whether the recomputed text differs from the stored one -
                the caller only writes a record on a True.
        """
        text = "\n".join(self.quality_findings(keywords))
        changed = text != self.insufficient_quality
        self.insufficient_quality = text
        return changed


class ServiceMetadata(MetadataTermsOfUse, AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer

        OR to store the information of the parsed iso metadata which was linked in the capabilities document.

    """
    service_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.RESTRICT,
                                        related_name="service_contact_%(class)s_metadata",
                                        verbose_name=_("service contact"),
                                        help_text=_("This is the contact for the service provider."))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.RESTRICT,
                                         related_name="metadata_contact_%(class)s_metadata",
                                         verbose_name=_("metadata contact"),
                                         help_text=_("This is the contact for the metadata information."))

    class Meta:
        abstract = True


class LayerMetadata(AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer.

        **Use cases**
            * 1. The stored information of this class will be transformed to iso metadata xml, which are stored in the
                 :class:`resource.Document` model.
            * 2. Searching for layer information

    """
    preview_image = models.ImageField(null=True, blank=True)

    class Meta:
        abstract = True

    # def save(self, *args, **kwargs):
    #    adding = self._state.adding
    #    super().save()
    #    if adding:
    #        xml = MdMetadata.from_field_dict(self.__dict__)
    #        xml_string = xml.serializeDocument()
    #        # FIXME: documents are created on the fly by registry.models.DocumentModelMixin
    #        Document.objects.create(layer_metadata=self,
    #                               xml=xml_string,
    #                              xml_backup=xml_string)


class FeatureTypeMetadata(AbstractMetadata):

    class Meta:
        abstract = True


class MetadataRelation(models.Model):
    """ Model to store relations between metadata models and service resource like models,

        to:
         * find available ogc services (wms, wfs, layer, feature_types) which can deliver relevant information by a filter constraint
         * to find metadata information by a filter constraint

        Note:
        This is the most important table in the system, to find concrete service data!
        This cross table allows us to join all the different model types in one database query

        Publication:
        Not every relation is published in the xml MrMap serves. The coupling policy is
        implemented by :class:`registry.querys.metadata.MetadataRelationQuerySet` and
        described in :attr:`publication_kind`. Only relations which are added by a curator
        with `origin=EDITOR` and `is_internal=True` contribute a metadata reference to the
        capabilities document of the related resource, see
        :attr:`registry.models.service.ServiceElement.published_metadata_links`.

    """
    # resource relations
    layer = models.ForeignKey(to="registry.Layer",
                              on_delete=models.CASCADE,
                              null=True,  # nullable to support polymorph using in MetadataRecord model
                              blank=True,
                              related_name="metadata_relations",
                              related_query_name="metadata_relation")
    feature_type = models.ForeignKey(to="registry.FeatureType",
                                     on_delete=models.CASCADE,
                                     null=True,  # nullable to support polymorph using in MetadataRecord model
                                     blank=True,
                                     related_name="metadata_relations",
                                     related_query_name="metadata_relation")
    csw = models.ForeignKey(to="registry.CatalogueService",
                            on_delete=models.CASCADE,
                            null=True,  # nullable to support polymorph using in MetadataRecord model
                            blank=True,
                            related_name="metadata_relations",
                            related_query_name="metadata_relation")
    wms = models.ForeignKey(to="registry.WebMapService",
                            on_delete=models.CASCADE,
                            null=True,  # nullable to support polymorph using in MetadataRecord model
                            blank=True,
                            related_name="metadata_relations",
                            related_query_name="metadata_relation")
    wfs = models.ForeignKey(to="registry.WebFeatureService",
                            on_delete=models.CASCADE,
                            null=True,  # nullable to support polymorph using in MetadataRecord model
                            blank=True,
                            related_name="metadata_relations",
                            related_query_name="metadata_relation")

    # metadata relations
    dataset_metadata = models.ForeignKey(to="DatasetMetadataRecord",
                                         on_delete=models.CASCADE,
                                         null=True,
                                         blank=True,
                                         related_name="resource_relations",
                                         related_query_name="resource_relation")

    service_metadata = models.ForeignKey(to="ServiceMetadataRecord",
                                         on_delete=models.CASCADE,
                                         null=True,
                                         blank=True,
                                         related_name="resource_relations",
                                         related_query_name="resource_relation")

    # relation describtive
    is_internal = models.BooleanField(default=False,
                                      verbose_name=_("internal relation?"),
                                      help_text=_("true means that this relation is created by a user and the dataset "
                                                  "is maybe not linked in a capabilities document for example."))
    origin = models.PositiveSmallIntegerField(choices=MetadataOriginEnum.choices,
                                              verbose_name=_("origin"),
                                              help_text=_("determines where this relation was found or it is added by a user."))

    objects = MetadataRelationManager()

    class Meta:

        constraints = [
            models.CheckConstraint(
                name="one_related_object_selected",
                condition=VALID_RELATIONS
            ),
            # service like resources can only have one describing service metadata
            models.UniqueConstraint(
                name="unique_service_metadata_representation_for_layer",
                fields=["service_metadata", "layer"]
            ),
            models.UniqueConstraint(
                name="unique_service_metadata_representation_for_feature_type",
                fields=["service_metadata", "feature_type"]
            ),
            models.UniqueConstraint(
                name="unique_service_metadata_representation_for_csw",
                fields=["service_metadata", "csw"]
            ),
            models.UniqueConstraint(
                name="unique_service_metadata_representation_for_wms",
                fields=["service_metadata", "wms"]
            ),
            models.UniqueConstraint(
                name="unique_service_metadata_representation_for_wfs",
                fields=["service_metadata", "wfs"]
            )
        ]

    @property
    def publication_kind(self):
        """ Return the kind of publication this relation contributes to the published xml.

            :return: the calculated publication kind
            :rtype: :class:`registry.enums.metadata.MetadataRelationPublicationEnum`
        """
        if not self.is_internal:
            return MetadataRelationPublicationEnum.IMPORTED_EVIDENCE
        if self.origin == MetadataOriginEnum.EDITOR.value:
            return MetadataRelationPublicationEnum.CURATED_PUBLICATION
        return MetadataRelationPublicationEnum.LOCAL_ONLY

    @property
    def is_publishable(self) -> bool:
        """ Return True if a curator added this relation with the intention to publish it. """
        return self.publication_kind == MetadataRelationPublicationEnum.CURATED_PUBLICATION

    @property
    def publication_url(self) -> str:
        """ Return the url which represents this relation in the published xml.

            The published reference is the location of the iso metadata document the
            linked dataset record was imported from. It is an empty string if the
            coupling can not be resolved to a printable location, see
            :attr:`publication_blockers`.

            :return: the url to publish or an empty string
            :rtype: str
        """
        if not self.is_publishable:
            return ""
        dataset = self.dataset_metadata
        if not dataset:
            return ""
        return dataset.origin_url or ""

    @property
    def publication_blockers(self) -> list:
        """ Return the reasons why this relation is not published.

            The strings are diagnostics for registry curators and are not translated.

            :return: a list with a reason for each blocker, empty if the relation is published
            :rtype: list
        """
        blockers = []
        if not self.is_publishable:
            blockers.append(
                f"relation of kind '{self.publication_kind.label}' is not intended for publication")
            return blockers
        if not self.dataset_metadata:
            blockers.append(
                "relation does not link a dataset metadata record, which is the only "
                "relation kind with a xml representation for a service element")
            return blockers
        if not self.dataset_metadata.origin_url:
            blockers.append(
                f"dataset metadata record '{self.dataset_metadata.file_identifier}' has no "
                f"origin url to publish")
        return blockers


class MetadataRecord(MetadataTermsOfUse, AbstractMetadata):

    # TODO: check if this is calculate able
    inspire_interoperability = models.BooleanField(default=False,
                                                   help_text=_("flag to signal if this "))

    harvested_through = models.ManyToManyField(to="registry.CatalogueService",
                                               related_name="%(app_label)s_%(class)s_metadata_records",
                                               related_query_name="%(app_label)s_%(class)s_metadata_record",
                                               editable=False,
                                               blank=True,
                                               verbose_name=_("services"),
                                               help_text=_("all services from which this dataset was harvested."))
    bounding_geometry = MultiPolygonField(null=True,
                                          blank=True, )
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.RESTRICT,
                                         related_name="%(class)s_metadata_contact",
                                         related_query_name="%(class)s_metadata_contact",
                                         verbose_name=_("contact"),
                                         help_text=_("this is the contact which is responsible for the metadata "
                                                     "information of the dataset."))
    reference_systems = models.ManyToManyField(to=ReferenceSystem,
                                               related_name="%(class)s",
                                               related_query_name="%(class)s",
                                               blank=True,
                                               verbose_name=_("reference systems"))
    equivalent_scale = models.FloatField(null=True,
                                         blank=True,
                                         editable=False,
                                         verbose_name=_("equivalent scale"),
                                         help_text=_("1 cm : 100 cm for example"))
    ground_res = models.FloatField(null=True,
                                   blank=True,
                                   editable=False,
                                   verbose_name=_("ground resolution"),
                                   help_text=_("pixel per meter for example"))
    code = models.CharField(max_length=4096,
                            blank=True,
                            default="",  # empty code signals broken dataset metadata records; means not inspire identifiable
                            help_text=_("identifier of the remote data"))
    code_space = models.CharField(max_length=4096,
                                  blank=True,
                                  default="",
                                  help_text=_("code space for the given identifier"))
    charset = models.PositiveSmallIntegerField(null=True,
                                               blank=True,
                                               choices=MetadataCharsetChoices.choices,
                                               verbose_name=_("charset"),
                                               help_text=_("full name of the character coding standard used for the metadata set"))

    time_extents = models.ManyToManyField(
        to=TimeExtent,
        blank=True,
        editable=False,
        related_name="%(app_label)s_%(class)s",
        related_query_name="%(app_label)s_%(class)s",
        verbose_name=_("time extent"),
        help_text=_(
            "all time extents which are available for this metadata record."),
    )

    resource_identifier = GeneratedField(
        expression=CombinedExpression(
            F("code_space"),
            "||",
            F("code"),
            output_field=models.CharField()
        ),
        output_field=models.CharField(),
        db_persist=True
    )

    # the keywords of the record as one denormalized array, kept in sync by the
    # database (see registry/migrations/0021_metadatarecords_keywords_list.py).
    # Aggregating the keywords relation is not expressible in a column expression,
    # so this array is what allows a searchable representation of a record to be a
    # column of the record itself instead of a projection which has to be rebuilt.
    # A write which brings a different array is answered by the relation instead
    # (registry/migrations/0024_keep_the_keywords_list_of_a_record_on_every_write.py).
    # The element follows the column of the keyword it copies: an array of a fixed
    # width would answer another text than the relation of the very same record and
    # would refuse the long keyword on the write of the record row, which is where
    # #894 would have landed otherwise. Widening it is what asks the generated
    # vector below to be rebuilt by the migration which changes this
    # (registry/migrations/0028_a_keyword_is_as_long_as_its_catalogue_says.py).
    keywords_list = ArrayField(
        base_field=models.TextField(),
        default=list,
        editable=False,
    )

    # columns which the database owns: a mapper must never send a value for them,
    # because the parsed instance only carries the default of the field -- the
    # database refuses such a value for the array itself, but a write which names a
    # maintained column is wrong even where no trigger watches it
    db_maintained_fields = ("keywords_list",)

    # the searchable representation of the record, computed by the database for every
    # row: a record is findable the moment it is written, without a projection which
    # has to be rebuilt and without a window in which it is not (the expression and
    # the reason it is written out instead of using SearchVector live in
    # registry/expressions/search.py)
    search_vector = GeneratedField(
        expression=MetadataRecordSearchVector(),
        output_field=SearchVectorField(),
        db_persist=True
    )

    class Meta:
        abstract = True

        constraints = [
            # we store only atomic dataset metadata records, identified by the remote url and the iso metadata file
            # identifier
            models.UniqueConstraint(
                fields=['file_identifier', 'code', 'code_space'],
                # empty values signals that, this dataset is broken.
                # This is a real world problem for that we support storing "duplicated" entries
                # For all correct dataset records the unique constraint shall be used!
                condition=~Q(code="", code_space=""),
                name='%(app_label)s_%(class)s_unique_together_code__and_code_space'),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_check_scale_xor_res",
                condition=Q(equivalent_scale=None, ground_res=None)
                | Q(equivalent_scale__gte=0, ground_res=None)
                | Q(equivalent_scale=None, ground_res__gte=0)
            )
        ] + AbstractMetadata.Meta.constraints

    def add_metadata_relation(self, related_object=None, origin=None, is_internal=False):

        kwargs = {}
        if related_object and related_object.__class__.__name__ == "Layer":
            kwargs.update({"layer": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value, })
        elif related_object and related_object.__class__.__name__ == "FeatureType":
            kwargs.update({"feature_type": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})
        elif related_object and related_object.__class__.__name__ == "WebMapService":
            kwargs.update({"wms": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})
        elif related_object and related_object.__class__.__name__ == "WebFeatureService":
            kwargs.update({"wfs": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})
        elif related_object and related_object.__class__.__name__ == "CatalogueService":
            kwargs.update({"csw": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})

        if self.__class__.__name__ == "DatasetMetadataRecord":
            kwargs.update({"dataset_metadata": self})
        elif self.__class__.__name__ == "ServiceMetadataRecord":
            kwargs.update({"service_metadata": self})

        with atomic():
            relation, _ = MetadataRelation.objects.select_for_update().get_or_create(
                is_internal=is_internal,
                **kwargs
            )
        return relation

    def remove_metadata_relation(self, related_object, internal, origin):
        kwargs = {}
        if related_object and related_object.__class__.__name__ == "Layer":
            kwargs.update({"layer": related_object})
        elif related_object and related_object.__class__.__name__ == "FeatureType":
            kwargs.update({"feature_type": related_object})
        elif related_object and related_object.__class__.__name__ == "WebMapService":
            kwargs.update({"wms": related_object})
        elif related_object and related_object.__class__.__name__ == "WebFeatureService":
            kwargs.update({"wfs": related_object})
        elif related_object and related_object.__class__.__name__ == "CatalogueService":
            kwargs.update({"csw": related_object})
        else:
            return

        if self.__class__.__name__ == "DatasetMetadataRecord":
            kwargs.update({"dataset_metadata": self})
        elif self.__class__.__name__ == "ServiceMetadataRecord":
            kwargs.update({"service_metadata": self})
        MetadataRelation.objects.select_for_update().filter(
            is_internal=internal,
            origin=origin,
            **kwargs
        ).delete()


class DatasetMetadataRecord(MetadataRecord):
    """ Concrete model class for dataset metadata records, which are parsed from iso metadata xml.

    """
    self_pointing_layers = models.ManyToManyField(to="registry.Layer",
                                                  through=MetadataRelation,
                                                  editable=False,
                                                  related_name="%(app_label)s_%(class)s_metadata_records",
                                                  related_query_name="%(app_label)s_%(class)s_metadata_record",
                                                  blank=True,
                                                  verbose_name=_("layers"),
                                                  help_text=_("all layers which are linking to this dataset metadata in"
                                                              " there capabilities."))
    self_pointing_feature_types = models.ManyToManyField(to="registry.FeatureType",
                                                         through=MetadataRelation,
                                                         editable=False,
                                                         related_name="%(app_label)s_%(class)s_metadata_records",
                                                         related_query_name="%(app_label)s_%(class)s_metadata_record",
                                                         blank=True,
                                                         verbose_name=_(
                                                             "feature types"),
                                                         help_text=_("all feature types which are linking to this "
                                                                     "dataset metadata in there capabilities."))
    dataset_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.RESTRICT,
                                        related_name="%(class)s_dataset_contact",
                                        related_query_name="%(class)s_dataset_contact",
                                        verbose_name=_("contact"),
                                        help_text=_("this is the contact which provides this dataset."))
    format = models.PositiveSmallIntegerField(null=True,
                                              blank=True,
                                              choices=DatasetFormatEnum.choices,
                                              verbose_name=_("format"),
                                              help_text=_("The format in which the described dataset is stored."))
    update_frequency_code = models.PositiveSmallIntegerField(choices=UpdateFrequencyChoices.choices,
                                                             null=True,
                                                             blank=True)
    inspire_top_consistence = models.BooleanField(default=False,
                                                  help_text=_("Flag to signal if the described data has a topologically"
                                                              " consistence."))
    preview_image = models.ImageField(null=True,
                                      blank=True)

    lineage_statement = models.TextField(blank=True,
                                         default="")
    categories = models.ManyToManyField(to=IsoCategory,
                                        blank=True,
                                        related_name="%(class)s_metadata",
                                        related_query_name="%(class)s_metadata",
                                        verbose_name=_("categories"),
                                        help_text=_("the topic categories of the dataset"))

    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields=("keywords_list", "search_vector",),
        bases=[AdditionalTimeFieldsHistoricalModel, DeltaSizeHistoricalModel],
    )

    objects = DatasetMetadataRecordManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("dataset metadata")
        verbose_name_plural = _("dataset metadata")
        constraints = [
        ] + MetadataRecord.Meta.constraints
        indexes = [
            models.Index(fields=["code", "code_space"]),
            # a record is found by its vector through a tsquery, which is a containment
            # over the vector and not a comparison of its text: only a GIN index answers it
            GinIndex(fields=["search_vector"]),
        ] + AbstractMetadata.Meta.indexes


class ServiceMetadataRecord(MetadataRecord):
    """ Concrete model class for service metadata records, which are parsed from iso metadata xml.

    """

    self_pointing_wms = models.ManyToManyField(to="registry.WebMapService",
                                                  through=MetadataRelation,
                                                  editable=False,
                                                  related_name="%(app_label)s_%(class)s_service_metadata",
                                                  related_query_name="%(app_label)s_%(class)s_service_metadata",
                                                  blank=True,
                                                  verbose_name=_(
                                                      "web map services"),
                                                  help_text=_("all wms which are linking to this service metadata in"
                                                              " there capabilities."))
    self_pointing_wfs = models.ManyToManyField(to="registry.WebFeatureService",
                                                  through=MetadataRelation,
                                                  editable=False,
                                                  related_name="%(app_label)s_%(class)s_service_metadata",
                                                  related_query_name="%(app_label)s_%(class)s_service_metadata",
                                                  blank=True,
                                                  verbose_name=_(
                                                      "web feature services"),
                                                  help_text=_("all wfs which are linking to this service metadata in"
                                                              " there capabilities."))
    self_pointing_csw = models.ManyToManyField(to="registry.CatalogueService",
                                                  through=MetadataRelation,
                                                  editable=False,
                                                  related_name="%(app_label)s_%(class)s_service_metadata",
                                                  related_query_name="%(app_label)s_%(class)s_service_metadata",
                                                  blank=True,
                                                  verbose_name=_(
                                                      "catalogue services"),
                                                  help_text=_("all csw which are linking to this service metadata in"
                                                              " there capabilities."))

    objects = ServiceMetadataRecordManager()
    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields=("keywords_list", "search_vector",),
        bases=[AdditionalTimeFieldsHistoricalModel, DeltaSizeHistoricalModel],
    )
    history = DefaultHistoryManager()

    class Meta:
        indexes = [
            # see DatasetMetadataRecord.Meta.indexes
            GinIndex(fields=["search_vector"]),
        ] + AbstractMetadata.Meta.indexes
        constraints = [

        ] + MetadataRecord.Meta.constraints


class ApplicationMetadataRecord(MetadataRecord):
    """ Concrete model class for application metadata records, which are parsed from iso metadata xml.

    An application record (gmd:hierarchyLevel = application) carries its identification
    as gmd:MD_DataIdentification in every catalogue sampled for #825 -- application
    records are shaped like dataset records, not like service records. This model
    therefore mirrors the dataset record: the party which provides the application,
    its topic categories and its maintenance frequency are read from the same elements.
    Fields which no sampled application record filled at all (fees, use limitation,
    licence, lineage) are not mirrored: the mapping config declares no input for them
    and nothing writes onto them until a catalogue actually publishes them.
    """

    application_contact = models.ForeignKey(to=MetadataContact,
                                            on_delete=models.RESTRICT,
                                            related_name="%(class)s_application_contact",
                                            related_query_name="%(class)s_application_contact",
                                            verbose_name=_("contact"),
                                            help_text=_("this is the contact which provides this application."))
    update_frequency_code = models.PositiveSmallIntegerField(choices=UpdateFrequencyChoices.choices,
                                                             null=True,
                                                             blank=True)
    categories = models.ManyToManyField(to=IsoCategory,
                                        blank=True,
                                        related_name="%(class)s_metadata",
                                        related_query_name="%(class)s_metadata",
                                        verbose_name=_("categories"),
                                        help_text=_("the topic categories of the application"))

    change_log = HistoricalRecords(
        related_name="change_logs",
        excluded_fields=("keywords_list", "search_vector",),
        bases=[AdditionalTimeFieldsHistoricalModel, DeltaSizeHistoricalModel],
    )

    objects = ApplicationMetadataRecordManager()
    history = DefaultHistoryManager()

    class Meta:
        verbose_name = _("application metadata")
        verbose_name_plural = _("application metadata")
        constraints = [
        ] + MetadataRecord.Meta.constraints
        indexes = [
            # see DatasetMetadataRecord.Meta.indexes
            models.Index(fields=["code", "code_space"]),
            GinIndex(fields=["search_vector"]),
        ] + AbstractMetadata.Meta.indexes


class DatasetMetadataRecordKeywordsLink(models.Model):
    """The keywords relation of the dataset records as an unmanaged model.

    The table is the one of the auto-created through model of
    ``DatasetMetadataRecord.keywords`` and stays created by it; this model only
    makes that table addressable by the migration autodetector, which is what a
    trigger of ``registry.triggers`` needs: triggers are declared on a model and
    the auto-created through models never enter the migration state (#1009).
    Being unmanaged, Django never creates, alters or drops the table through it.
    """

    datasetmetadatarecord = models.ForeignKey(
        to="registry.DatasetMetadataRecord",
        on_delete=models.CASCADE,
        related_name="d_keywords_link+")
    keyword = models.ForeignKey(
        to="registry.Keyword",
        on_delete=models.CASCADE,
        related_name="d_keywords_link+")

    class Meta:
        db_table = "registry_datasetmetadatarecord_keywords"
        managed = False


class ServiceMetadataRecordKeywordsLink(models.Model):
    """The keywords relation of the service records, see the dataset one above."""

    servicemetadatarecord = models.ForeignKey(
        to="registry.ServiceMetadataRecord",
        on_delete=models.CASCADE,
        related_name="s_keywords_link+")
    keyword = models.ForeignKey(
        to="registry.Keyword",
        on_delete=models.CASCADE,
        related_name="s_keywords_link+")

    class Meta:
        db_table = "registry_servicemetadatarecord_keywords"
        managed = False


class ApplicationMetadataRecordKeywordsLink(models.Model):
    """The keywords relation of the application records, see the dataset one above."""

    applicationmetadatarecord = models.ForeignKey(
        to="registry.ApplicationMetadataRecord",
        on_delete=models.CASCADE,
        related_name="a_keywords_link+")
    keyword = models.ForeignKey(
        to="registry.Keyword",
        on_delete=models.CASCADE,
        related_name="a_keywords_link+")

    class Meta:
        db_table = "registry_applicationmetadatarecord_keywords"
        managed = False
