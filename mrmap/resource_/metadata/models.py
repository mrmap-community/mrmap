from django.contrib.gis.db.models import MultiPolygonField
from django.db import models
from django.utils.translation import gettext_lazy as _
from uuid import uuid4

from main.models import GenericModelMixin, CommonInfo
from resource_.service_.models import Layer, FeatureType, Service
from structure.models import Contact
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Licence(UuidPk):
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255, unique=True)
    symbol_url = models.URLField(null=True)
    description = models.TextField()
    description_url = models.URLField(null=True)
    is_open_data = models.BooleanField(default=False)

    def __str__(self):
        return "{} ({})".format(self.identifier, self.name)

    @classmethod
    def as_choices(cls):
        """ Returns a list of (identifier, name) to be used as choices in a form

        Returns:
             tuple_list (list): As described above
        """
        return [(licence.identifier, licence.__str__()) for licence in Licence.objects.filter(is_active=True)]

    @classmethod
    def get_descriptions_help_text(cls):
        """ Returns a string containing all Licence records for rendering as help_text in a form

        Returns:
             string (str): As described above
        """
        from django.db.utils import ProgrammingError

        try:
            descrs = [
                "<a href='{}' target='_blank'>{}</a>".format(
                    licence.description_url, licence.identifier
                ) for licence in Licence.objects.all()
            ]
            descr_str = "<br>".join(descrs)
            descr_str = _("Explanations: <br>") + descr_str
        except (ProgrammingError, OperationalError):
            # This will happen on an initial installation. The Licence table won't be created yet, but this function
            # will be called on makemigrations.
            descr_str = ""
        return descr_str


class ReferenceSystem(models.Model):
    pass
    # todo


class Dimension(models.Model):
    pass
    # todo


class MetadataContact(Contact):
    name = models.CharField(verbose_name=_("Name"),
                            default="",
                            help_text=_("The name of the organization"),
                            max_length=256)

    class Meta:
        ordering = ["name"]


class Keyword(models.Model):
    keyword = models.CharField(max_length=255,
                               unique=True,
                               db_index=True)

    def __str__(self):
        return self.keyword

    class Meta:
        ordering = ["keyword"]


class MimeType(models.Model):
    mime_type = models.CharField(max_length=500,
                                 unique=True,
                                 db_index=True,
                                 verbose_name=_("mime type"),
                                 help_text=_("The Internet Media Type"))

    def __str__(self):
        return self.mime_type


class RemoteMetadata(models.Model):
    """ Concrete model class to store linked iso metadata records while registration processing to fetch them after
        the service was registered. This helps us to parallelize the download processing with a celery group or
        something else.

    """
    mime_type = models.ForeignKey(to=MimeType,
                                  on_delete=models.SET_NULL,
                                  related_name="remote_metadata",
                                  related_query_name="remote_metadata",
                                  verbose_name=_("mime type"),
                                  help_text=_("the mime type of the the remote metadata"))
    link = models.URLField(max_length=4094,
                           verbose_name=_("download link"),
                           help_text=_("the url where the metadata could be downloaded from."))
    remote_content = models.TextField(null=True,
                                      verbose_name=_("remote content"),
                                      help_text=_("the fetched content of the download url."))
    service = models.ForeignKey(to=Service,
                                on_delete=models.CASCADE,
                                related_name="remote_metadata",
                                related_query_name="remote_metadata",
                                verbose_name=_("service"),
                                help_text=_("the service where this remote metadata is related to. This remote metadata"
                                            " was found in the GetCapabilites document of the related service."))
    content_type = models.ForeignKey(to=ContentType,
                                     on_delete=models.CASCADE)
    object_id = models.UUIDField(verbose_name=_("described resource"),
                                 help_text=_("the uuid of the described service, layer or feature type"))
    describes = GenericForeignKey(ct_field='content_type',
                                  fk_field='object_id',)


class MetadataTermsOfUse(models.Model):
    """ Abstract model class to define some fields which describes the terms of use for an metadata

    """
    access_constraints = models.TextField(default="",
                                          verbose_name=_("access constraints"),
                                          help_text=_("access constraints for the given resource."))
    fees = models.TextField(default="",
                            verbose_name=_("fees"),
                            help_text=_("Costs and of terms of use for the given resource."))
    use_limitation = models.TextField(default="")
    license_source_note = models.TextField()
    licence = models.ForeignKey(Licence, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        abstract = True


class AbstractMetadata(GenericModelMixin, CommonInfo):
    """ Abstract model class to define general fields for all concrete metadata models. """
    id = models.UUIDField(primary_key=True,
                          default=uuid4,
                          editable=False)
    file_identifier = models.CharField(max_length=1000,
                                       default="",
                                       editable=False,
                                       verbose_name=_("file identifier"),
                                       help_text=_("the parsed file identifier from the iso metadata xml "
                                                   "(gmd:fileIdentifier) OR for example if it is a layer/featuretype"
                                                   "the uuid of the described layer/featuretype shall be used to "
                                                   "identify the generated iso metadata xml."))
    origin = models.CharField(choices="TODO",
                              editable=False,
                              verbose_name=_("origin"),
                              help_text=_("Where the metadata record comes from."))
    origin_url = models.URLField(null=True,
                                 blank=True,
                                 editable=False,
                                 verbose_name=_("origin url"),
                                 help_text=_("the url of the document where the information of this metadata record "
                                             "comes from"))
    title = models.CharField(max_length=1000,
                             verbose_name=_("title"),
                             help_text=_("a short descriptive title for this metadata"))
    abstract = models.TextField(default='',
                                verbose_name=_("abstract"),
                                help_text=_("brief summary of the content of this metadata."))
    is_broken = models.BooleanField(default=False,
                                    editable=False,
                                    verbose_name=_("is broken"),
                                    help_text=_("TODO"))
    is_searchable = models.BooleanField(default=False,
                                        help_text=_(""))
    # todo: do we need this flag?
    is_custom = models.BooleanField(default=False,
                                    editable=False)
    hits = models.IntegerField(default=0,
                               verbose_name=_("hits"),
                               help_text=_("how many times this metadata was requested by a client"),
                               editable=False,)
    keywords = models.ManyToManyField(to=Keyword,
                                      related_name="%(class)s_metadata",
                                      related_query_name="%(class)s_metadata",
                                      verbose_name=_("keywords"),
                                      help_text=_("all keywords which are related to the content of this metadata."))

    class Meta:
        abstract = True
        ordering = ["title"]

    def __str__(self):
        return self.title


class ServiceMetadata(MetadataTermsOfUse, AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer

        OR to store the information of the parsed iso metadata which was linked in the capabilities document.

    """
    described_resource = models.OneToOneField(to=Service,
                                              on_delete=models.CASCADE,
                                              related_name="service_metadata",
                                              related_query_name="service_metadata",
                                              verbose_name=_("described service"),
                                              help_text=_("choice the service you want to describe with this metadata"))
    service_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.SET_NULL,
                                        related_name="service_metadata",
                                        related_query_name="service_metadata",
                                        verbose_name=_("contact"),
                                        help_text=_(""))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.SET_NULL,
                                         related_name="service_metadata",
                                         related_query_name="service_metadata",
                                         verbose_name=_("contact"),
                                         help_text=_(""))

    class Meta:
        verbose_name = _("service metadata")
        verbose_name_plural = _("service metadata")


class LayerMetadata(AbstractMetadata):
    """ Concrete model class to store the parsed metadata information from the capabilities document of a given layer.

        **Use cases**
            * 1. The stored information of this class will be transformed to iso metadata xml, which are stored in the
                 :class:`resource.Document` model.
            * 2. Searching for layer information

        # todo: if an instance of this model is created an instance of the model `Document`, who stores the generated
                xml, shall be created.
        # todo: if an instance of this model is updated the related instance of the model `Document` shall be updated.
    """
    described_resource = models.OneToOneField(to=Layer,
                                              on_delete=models.CASCADE,
                                              related_name="layer_metadata",
                                              related_query_name="layer_metadata",
                                              verbose_name=_("described layer"),
                                              help_text=_("choice the layer you want to describe with this metadata"))
    reference_systems = models.ManyToManyField(to=ReferenceSystem,
                                               related_name="layer_metadata",
                                               related_query_name="layer_metadata",
                                               blank=True,
                                               verbose_name=_("reference systems"))
    dimensions = models.ManyToManyField(to=Dimension,
                                        related_name="layer_metadata",
                                        related_query_name="layer_metadata",
                                        blank=True,
                                        verbose_name=_("dimensions"))
    preview_image = None  # todo

    class Meta:
        verbose_name = _("layer metadata")
        verbose_name_plural = _("layer metadata")


class FeatureTypeMetadata(models.Model):
    described_resource = models.OneToOneField(to=FeatureType,
                                              on_delete=models.CASCADE,
                                              related_name="feature_type_metadata",
                                              related_query_name="feature_type_metadata",
                                              verbose_name=_("described feature type"),
                                              help_text=_("choice the feature type you want to describe with this "
                                                          "metadata"))

    class Meta:
        verbose_name = _("feature type metadata")
        verbose_name_plural = _("feature type metadata")


class DatasetMetadata(MetadataTermsOfUse, AbstractMetadata):
    SRS_AUTHORITIES_CHOICES = [
        ("EPSG", "European Petroleum Survey Group (EPSG) Geodetic Parameter Registry"),
    ]

    CHARACTER_SET_CHOICES = [
        ("utf8", "utf8"),
        ("utf16", "utf16"),
    ]

    UPDATE_FREQUENCY_CHOICES = [
        ("annually", "annually"),
        ("asNeeded", "asNeeded"),
        ("biannually", "biannually"),
        ("irregular", "irregular"),
        ("notPlanned", "notPlanned"),
        ("unknown", "unknown"),
    ]

    LEGAL_RESTRICTION_CHOICES = [
        ("copyright", "copyright"),
        ("intellectualPropertyRights", "intellectualPropertyRights"),
        ("license", "license"),
        ("otherRestrictions", "otherRestrictions"),
        ("patent", "patent"),
        ("patentPending", "patentPending"),
        ("restricted", "restricted"),
        ("trademark", "trademark"),
    ]

    DISTRIBUTION_FUNCTION_CHOICES = [
        ("download", "download"),
        ("information", "information"),
        ("offlineAccess", "offlineAccess"),
        ("order", "order"),
        ("search", "search"),
    ]

    DATA_QUALITY_SCOPE_CHOICES = [
        ("attribute", "attribute"),
        ("attributeType", "attributeType"),
        ("collectionHardware", "collectionHardware"),
        ("collectionSession", "collectionSession"),
        ("dataset", "dataset"),
        ("dimensionGroup", "dimensionGroup"),
        ("feature", "feature"),
        ("featureType", "featureType"),
        ("fieldSession", "fieldSession"),
        ("model", "model"),
        ("nonGeographicDataset", "nonGeographicDataset"),
        ("propertyType", "propertyType"),
        ("series", "series"),
        ("software", "software"),
        ("service", "service"),
        ("tile", "tile"),
    ]

    LANGUAGE_CODE_LIST_URL_DEFAULT = "https://standards.iso.org/iso/19139/Schemas/resources/codelist/ML_gmxCodelists.xml"
    CODE_LIST_URL_DEFAULT = "https://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml"
    dataset_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.SET_NULL,
                                        related_name="dataset_metadata",
                                        related_query_name="service_metadata",
                                        verbose_name=_("contact"),
                                        help_text=_(""))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.SET_NULL,
                                         related_name="dataset_metadata",
                                         related_query_name="dataset_metadata",
                                         verbose_name=_("contact"),
                                         help_text=_(""))
    temporal_extent_start = models.DateTimeField(verbose_name=_("time period start"),
                                                 help_text=_("the start of the period in which the represented data was"
                                                             " collected."))
    temporal_extent_end = models.DateTimeField(verbose_name=_("time period end"),
                                               help_text=_("the end of the period in which the represented data was "
                                                           "collected."))
    spatial_res_type = models.CharField(max_length=100,
                                        choices=[("groundDistance", ""), ("scaleDenominator", "")],
                                        verbose_name=_("resolution type"),
                                        help_text=_("Ground resolution in meter or the equivalent scale."))
    spatial_res_value = models.FloatField(verbose_name=_("resolution value"),
                                          help_text=_("The value depending on the selected resolution type."))
    reference_systems = models.ManyToManyField(to=ReferenceSystem,
                                               related_name="layer_metadata",
                                               related_query_name="layer_metadata",
                                               blank=True,
                                               verbose_name=_("reference systems"))
    format = models.CharField(max_length=100,
                              choices=["Database", "Esri shape", "CSV", "GML", "GeoTIFF"],
                              verbose_name=_("format"),
                              help_text=_("The format in which the described dataset is stored."))
    charset = models.CharField(max_length=100,
                               choices=["utf8"],
                               verbose_name=_("charset"),
                               help_text=_("The charset which is used by the stored data."))
    inspire_top_consistence = models.BooleanField(help_text=_("Flag to signal if the described data has a topologically"
                                                              " consistence."))
    preview_image = None  # todo
    lineage_statement = models.TextField(null=True, blank=True)

    update_frequency_code = models.CharField(max_length=255, choices=UPDATE_FREQUENCY_CHOICES, null=True, blank=True)

    bounding_geometry = MultiPolygonField(default=MultiPolygonField(
        (
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
        )
    ))
    dataset_id = models.CharField(max_length=4000,
                                  help_text=_("identifier of the remote data"))
    dataset_id_code_space = models.CharField(max_length=100,
                                             help_text=_("code space for the given identifier"))
    inspire_interoperability = models.BooleanField(default=False,
                                                   help_text=_("flag to signal if this "))
