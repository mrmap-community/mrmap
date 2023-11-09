from uuid import uuid4

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db.models import MultiPolygonField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from extras.managers import UniqueConstraintDefaultValueManager
from MrMap.settings import PROXIES
from ows_lib.xml_mapper.iso_metadata.iso_metadata import (MdMetadata,
                                                          WrappedIsoMetadata)
from registry.enums.metadata import (DatasetFormatEnum, MetadataCharset,
                                     MetadataOriginEnum,
                                     ReferenceSystemPrefixEnum)
from registry.exceptions.service import NoContent
from registry.managers.metadata import IsoMetadataManager, KeywordManager
from registry.models.document import MetadataDocumentModelMixin
from registry.models.metadata_query import VALID_RELATIONS
from requests import Request, Session
from requests.adapters import HTTPAdapter
from urllib3 import Retry


class MimeType(models.Model):
    mime_type = models.CharField(max_length=500,
                                 unique=True,
                                 db_index=True,
                                 verbose_name=_("mime type"),
                                 help_text=_("The Internet Media Type"))

    def __str__(self):
        return self.mime_type


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
    code = models.CharField(max_length=100)
    prefix = models.CharField(max_length=255,
                              choices=ReferenceSystemPrefixEnum.choices,
                              default=ReferenceSystemPrefixEnum.EPSG.value)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code', 'prefix'],
                                    name='%(app_label)s_%(class)s_unique_code_prefix')
        ]
        ordering = ["-code"]

    def __str__(self):
        return f"{self.prefix}:{self.code}" if self.prefix else self.code

    def __eq__(self, __value: object) -> bool:
        return self.code == __value.code and self.prefix == __value.prefix


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
    keyword = models.CharField(max_length=255,
                               unique=True,
                               db_index=True,)

    objects = KeywordManager()

    def __str__(self):
        return self.keyword

    class Meta:
        ordering = ["keyword"]

    def natural_key(self):
        return (self.keyword,)


class RemoteMetadata(models.Model):
    """ Concrete model class to store linked iso metadata records while registration processing to fetch them after
        the service was registered. This helps us to parallelize the download processing with a celery group.

        To create the concrete metadata records the following workflow is necessary:
            1. fetch the remote content with fetch_remote_content(). After that the remote content was fetched.
            2. create the concrete metadata record (ServiceMetadataRecord | DatasetMetadataRecord) with create_metadata_instance()

        todo: maybe this model could be refactored as general document class
    """
    # todo: set link unique. IF we found one RemoteMetadata object with the same link, we can copy it and update the
    #  service fk to the service which was registered. Additional: we need to refactor the GenericForeignKey... We need
    #  then m2m relations to layers, featuretypes and services
    link = models.URLField(max_length=4094,
                           verbose_name=_("download link"),
                           help_text=_("the url where the metadata could be downloaded from."))
    remote_content = models.TextField(null=True,
                                      verbose_name=_("remote content"),
                                      help_text=_("the fetched content of the download url."))
    content_type = models.ForeignKey(to=ContentType,
                                     on_delete=models.CASCADE)
    object_id = models.UUIDField(verbose_name=_("described resource"),
                                 help_text=_("the uuid of the described service, layer or feature type"))
    describes = GenericForeignKey(ct_field='content_type',
                                  fk_field='object_id', )

    class Meta:
        abstract = True

    def fetch_remote_content(self, save=True):
        """ Return the fetched remote content and update the content if save is True """

        session = Session()
        session.proxies = PROXIES
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

    def parse(self):
        """ Return the parsed self.remote_content

            Raises:
                ValueError: if self.remote_content is null
        """
        if self.remote_content:
            self.parsed_metadata = xmlmap.load_xmlobject_from_string(string=bytes(self.remote_content, "UTF-8"),
                                                                     xmlclass=WrappedIsoMetadata)
            return self.parsed_metadata.iso_metadata[0]
        else:
            raise ValueError(
                "there is no fetched content. You need to call fetch_remote_content() first.")

    def create_metadata_instance(self, **kwargs):
        """ Return the created metadata record, based on the content_type of the described element. """
        from registry.models.service import (CatalogueService,
                                             WebFeatureService, WebMapService)
        if isinstance(self.describes, (WebMapService, WebFeatureService, CatalogueService)):
            metadata_cls = ServiceMetadataRecord
        else:
            metadata_cls = DatasetMetadataRecord
        db_metadata, _, _ = metadata_cls.iso_metadata.update_or_create_from_parsed_metadata(parsed_metadata=self.parse(),
                                                                                            related_object=self.describes,
                                                                                            origin_url=self.link,
                                                                                            **kwargs)
        return db_metadata


class WebMapServiceRemoteMetadata(RemoteMetadata):
    service = models.ForeignKey(to="registry.WebMapService",
                                on_delete=models.CASCADE,
                                related_name="remote_metadata",
                                related_query_name="remote_metadata",
                                verbose_name=_("web map service"),
                                help_text=_("the service where this remote metadata is related to. This remote metadata"
                                            " was found in the GetCapabilites document of the related service."))


class WebFeatureServiceRemoteMetadata(RemoteMetadata):
    service = models.ForeignKey(to="registry.WebFeatureService",
                                on_delete=models.CASCADE,
                                related_name="remote_metadata",
                                related_query_name="remote_metadata",
                                verbose_name=_("web map service"),
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
                                      auto_now_add=True,
                                      editable=False,
                                      db_index=True)
    file_identifier = models.CharField(max_length=1000,
                                       null=True,
                                       editable=False,
                                       default=uuid4,
                                       db_index=True,
                                       verbose_name=_("file identifier"),
                                       help_text=_("the parsed file identifier from the iso metadata xml "
                                                   "(gmd:fileIdentifier) OR for example if it is a layer/featuretype"
                                                   "the uuid of the described layer/featuretype shall be used to "
                                                   "identify the generated iso metadata xml."))
    origin = models.CharField(max_length=20,
                              choices=MetadataOriginEnum.choices,
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
    title: str = models.CharField(max_length=1000,
                                  verbose_name=_("title"),
                                  help_text=_("a short descriptive title for this metadata"))
    abstract = models.TextField(null=True,
                                verbose_name=_("abstract"),
                                help_text=_("brief summary of the content of this metadata."))
    is_broken = models.BooleanField(default=False,
                                    editable=False,
                                    verbose_name=_("is broken"),
                                    help_text=_("TODO"))
    is_customized = models.BooleanField(default=False,
                                        editable=False,
                                        verbose_name=_("is customized"),
                                        help_text=_("If the metadata record is customized, this flag is True"))
    insufficient_quality = models.TextField(null=True,
                                            blank=True,
                                            help_text=_("TODO"))
    is_searchable = models.BooleanField(default=False,
                                        verbose_name=_("is searchable"),
                                        help_text=_("only searchable metadata will be returned from the search api"))
    hits = models.IntegerField(default=0,
                               verbose_name=_("hits"),
                               help_text=_(
                                   "how many times this metadata was requested by a client"),
                               editable=False, )
    keywords = models.ManyToManyField(to=Keyword,
                                      related_name="%(class)s_metadata",
                                      related_query_name="%(class)s_metadata",
                                      verbose_name=_("keywords"),
                                      help_text=_("all keywords which are related to the content of this metadata."))

    language = None  # TODO
    category = None  # TODO: Inspire + iso + various

    # needed for Docuement mixin to load the backupfile into the correct xml mapper class
    xml_mapper_cls = MdMetadata

    class Meta:
        abstract = True
        ordering = ["title"]
        indexes = [
            models.Index(fields=["file_identifier", "title"])
        ]
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_unique_file_identifier",
                fields=["file_identifier"]
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.pk})"

    def save(self, *args, **kwargs):
        """Custom save function to set `is_customized` on update."""
        # FIXME: if the record is updated by harvesting process, the customized flag shall not be set to True
        if not self._state.adding:
            self.is_customized = True
        super().save(*args, **kwargs)


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
    iso_metadata = IsoMetadataManager()

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
    origin = models.CharField(max_length=20,
                              choices=MetadataOriginEnum.choices,
                              verbose_name=_("origin"),
                              help_text=_("determines where this relation was found or it is added by a user."))

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="one_related_object_selected",
                check=VALID_RELATIONS
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


class MetadataRecord(MetadataTermsOfUse, AbstractMetadata):
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
    harvested_through = models.ManyToManyField(to="registry.CatalogueService",
                                               related_name="%(app_label)s_%(class)s_metadata_records",
                                               related_query_name="%(app_label)s_%(class)s_metadata_record",
                                               editable=False,
                                               blank=True,
                                               verbose_name=_("services"),
                                               help_text=_("all services from which this dataset was harvested."))

    class Meta:
        abstract = True

    iso_metadata = IsoMetadataManager()


class DatasetMetadataRecord(MetadataRecord):
    """ Concrete model class for dataset metadata records, which are parsed from iso metadata xml.

    """
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

    SPATIAL_RES_TYPE_CHOICES = [("groundDistance", "groundDistance"),
                                ("scaleDenominator", "scaleDenominator")]

    INDETERMINATE_POSITION_CHOICES = [
        ("now", "now"), ("before", "before"), ("after", "after"), ("unknown", "unknown")]

    LANGUAGE_CODE_LIST_URL_DEFAULT = "https://standards.iso.org/iso/19139/Schemas/resources/codelist/ML_gmxCodelists.xml"
    CODE_LIST_URL_DEFAULT = "https://www.isotc211.org/2005/resources/Codelist/gmxCodelists.xml"

    dataset_contact = models.ForeignKey(to=MetadataContact,
                                        on_delete=models.RESTRICT,
                                        related_name="dataset_contact_metadata",
                                        related_query_name="dataset_contact_metadata",
                                        verbose_name=_("contact"),
                                        help_text=_("this is the contact which provides this dataset."))
    metadata_contact = models.ForeignKey(to=MetadataContact,
                                         on_delete=models.RESTRICT,
                                         related_name="metadata_contact_metadata",
                                         related_query_name="metadata_contact_metadata",
                                         verbose_name=_("contact"),
                                         help_text=_("this is the contact which is responsible for the metadata "
                                                     "information of the dataset."))
    spatial_res_type = models.CharField(max_length=20,
                                        choices=SPATIAL_RES_TYPE_CHOICES,
                                        default="",
                                        verbose_name=_("resolution type"),
                                        help_text=_("Ground resolution in meter or the equivalent scale."))
    spatial_res_value = models.FloatField(null=True,
                                          blank=True,
                                          verbose_name=_("resolution value"),
                                          help_text=_("The value depending on the selected resolution type."))
    reference_systems = models.ManyToManyField(to=ReferenceSystem,
                                               related_name="dataset_metadata",
                                               related_query_name="dataset_metadata",
                                               blank=True,
                                               verbose_name=_("reference systems"))
    format = models.CharField(default="",
                              blank=True,
                              max_length=20,
                              choices=DatasetFormatEnum.choices,
                              verbose_name=_("format"),
                              help_text=_("The format in which the described dataset is stored."))
    charset = models.CharField(default="",
                               blank=True,
                               max_length=10,
                               choices=MetadataCharset.choices,
                               verbose_name=_("charset"),
                               help_text=_("The charset which is used by the stored data."))
    inspire_top_consistence = models.BooleanField(default=False,
                                                  help_text=_("Flag to signal if the described data has a topologically"
                                                              " consistence."))
    preview_image = models.ImageField(null=True,
                                      blank=True)
    lineage_statement = models.TextField(blank=True,
                                         default="")
    update_frequency_code = models.CharField(max_length=20,
                                             choices=UPDATE_FREQUENCY_CHOICES,
                                             blank=True,
                                             default="")
    bounding_geometry = MultiPolygonField(null=True,
                                          blank=True, )
    dataset_id = models.CharField(max_length=4096,
                                  default="",  # empty dataset_id signals broken dataset metadata records
                                  help_text=_("identifier of the remote data"))
    dataset_id_code_space = models.CharField(max_length=4096,
                                             blank=True,
                                             default="",
                                             help_text=_("code space for the given identifier"))
    inspire_interoperability = models.BooleanField(default=False,
                                                   help_text=_("flag to signal if this "))

    objects = UniqueConstraintDefaultValueManager()

    class Meta:
        verbose_name = _("dataset metadata")
        verbose_name_plural = _("dataset metadata")
        constraints = [
            # we store only atomic dataset metadata records, identified by the remote url and the iso metadata file
            # identifier
            models.UniqueConstraint(
                fields=['dataset_id', 'dataset_id_code_space'],
                # empty values signals that, this dataset is broken.
                # This is a real world problem for that we support storing "duplicated" entries
                # For all correct dataset records the unique constraint shall be used!
                condition=~Q(dataset_id="", dataset_id_code_space=""),
                name='%(app_label)s_%(class)s_unique_together_dataset_id_dataset_id_code_space')
        ]
        indexes = [
            models.Index(fields=["dataset_id", "dataset_id_code_space"])
        ]

    def add_dataset_metadata_relation(self, related_object=None, origin=None, is_internal=False):
        from registry.models.service import FeatureType, Layer

        kwargs = {}
        if related_object and related_object._meta.model == Layer:
            kwargs.update({"layer": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})
        elif related_object and related_object._meta.model == FeatureType:
            kwargs.update({"feature_type": related_object,
                           "origin": origin if origin else MetadataOriginEnum.CAPABILITIES.value})

        relation, _ = MetadataRelation.objects.get_or_create(
            dataset_metadata=self,
            is_internal=is_internal,
            **kwargs
        )
        return relation

    def remove_dataset_metadata_relation(self, related_object, internal, origin):
        from registry.models.service import FeatureType, Layer

        kwargs = {}
        if related_object._meta.model == Layer:
            kwargs.update({"layer": related_object})
        elif related_object._meta.model == FeatureType:
            kwargs.update({"feature_type": related_object})
        else:
            return
        MetadataRelation.objects.filter(
            dataset_metadata=self,
            is_internal=internal,
            origin=origin,
            **kwargs
        ).delete()


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
    self_pointing_wfs = models.ManyToManyField(to="registry.CatalogueService",
                                                  through=MetadataRelation,
                                                  editable=False,
                                                  related_name="%(app_label)s_%(class)s_service_metadata",
                                                  related_query_name="%(app_label)s_%(class)s_service_metadata",
                                                  blank=True,
                                                  verbose_name=_(
                                                      "catalogue services"),
                                                  help_text=_("all csw which are linking to this service metadata in"
                                                              " there capabilities."))


class Dimension(models.Model):
    # TODO: refactor this class to conrete models for layer and dataset
    name = models.CharField(max_length=50,
                            verbose_name=_("name"),
                            help_text=_("the type of the content stored in extent field."))
    units = models.CharField(max_length=50,
                             verbose_name=_("units"),
                             help_text=_("measurement units specifier"))
    parsed_extent = models.TextField(verbose_name=_("extent"),
                                     help_text=_("The extent string declares what value(s) along the Dimension axis are"
                                                 " appropriate for this specific geospatial data object."))
    layer = models.ForeignKey(to="registry.Layer",
                              on_delete=models.CASCADE,
                              null=True,
                              blank=True,
                              related_name="layer_dimensions",
                              related_query_name="layer_dimension",
                              verbose_name=_("layer"),
                              help_text=_("the related layer of this dimension entity"))
    # FIXME: Featuretypes does not have any dimensions
    feature_type = models.ForeignKey(to="registry.FeatureType",
                                     on_delete=models.CASCADE,
                                     null=True,
                                     blank=True,
                                     related_name="feature_type_dimensions",
                                     related_query_name="feature_type_dimension",
                                     verbose_name=_("feature type"),
                                     help_text=_("the related feature type of this dimension entity"))
    dataset_metadata = models.ForeignKey(to=DatasetMetadataRecord,
                                         on_delete=models.CASCADE,
                                         null=True,
                                         blank=True,
                                         related_name="dataset_metadata_dimensions",
                                         related_query_name="dataset_metadata_dimension",
                                         verbose_name=_("dataset metadata"),
                                         help_text=_("the related dataset metadata of this dimension entity"))

    def clean(self):
        """ Raise ValidationError if layer and feature type and dataset metadata are null or if two of them
            are configured.
        """
        if not self.layer and not self.feature_type and self.dataset_metadata:
            raise ValidationError(
                "either layer, feature type or dataset metadata must be linked.")
        elif self.layer and self.feature_type or \
                self.layer and self.dataset_metadata or \
                self.feature_type and self.dataset_metadata:
            raise ValidationError(
                "link two or more related objects is not supported.")


class TimeExtent(models.Model):
    start = models.DateTimeField()
    # FIXME: allow null=True, to signal no ending time interval
    stop = models.DateTimeField()
    # null signals infinity resolution or a single value if start and stop is equal
    resolution = models.DurationField(null=True)
    dimension = models.ForeignKey(to=Dimension,
                                  on_delete=models.CASCADE,
                                  related_name="time_extents",
                                  related_query_name="time_extent",
                                  verbose_name=_("related dimension"),
                                  help_text=_("the related dimension where this interval was found."))
