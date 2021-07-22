from django.db import models
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from main.models import CommonInfo
from resourceNew.enums.document import DocumentEnum
from resourceNew.models import ServiceMetadata, LayerMetadata, FeatureTypeMetadata, DatasetMetadata, Service, Layer, \
    FeatureType
from eulxml import xmlmap
from resourceNew.xmlmapper.iso_metadata.iso_metadata import WrappedIsoMetadata
from resourceNew.xmlmapper.ogc.capabilities import get_parsed_service


class Document(CommonInfo):
    """Model to store documents such as capabilities or ISO MD_Metadata xml for different related objects.

    :attr service: This document stores the capabilities document for the related
     :class:`resourceNew.models.service.Service` service.
    :attr layer: This document stores the capabilities document for the related
     :class:`resourceNew.models.service.Layer` which contains only the single layer information.
    :attr feature_type: This document stores the capabilities document for the related
     :class:`resourceNew.models.service.FeatureType` which contains only the single feature type information.

    :attr service_metadata: This document stores the iso MD_Metadata xml representation for the related
     :class:`resourceNew.models.metadata.ServiceMetadata` which describes the service.
    :attr layer_metadata: This document stores the iso MD_Metadata xml representation for the related
     :class:`resourceNew.models.metadata.LayerMetadata` which describes this single layer as a service.
    :attr feature_type_metadata: This document stores the iso MD_Metadata xml representation for the related
     :class:`resourceNew.models.metadata.FeatureTypeMetadata` which describes this single feature type as a service.
    :attr dataset_metadata: This document stores the iso MD_Metadata xml representation for the related
     :class:`resourceNew.models.metadata.DatasetMetadata`.

    """
    HELP_TEXT = _("the metadata object which is parsed from this xml.")
    service = models.OneToOneField(to=Service,
                                   on_delete=models.CASCADE,
                                   null=True,
                                   blank=True,
                                   related_name="document",
                                   related_query_name="document",
                                   verbose_name=_("related service"),
                                   help_text=_("the service object which is described by this capabilities document."))
    layer = models.OneToOneField(to=Layer,
                                 on_delete=models.CASCADE,
                                 null=True,
                                 blank=True,
                                 related_name="document",
                                 related_query_name="document",
                                 verbose_name=_("related layer"),
                                 help_text=_("the layer object which is described by this capabilities document."))
    feature_type = models.OneToOneField(to=FeatureType,
                                        on_delete=models.CASCADE,
                                        null=True,
                                        blank=True,
                                        related_name="document",
                                        related_query_name="document",
                                        verbose_name=_("related feature type"),
                                        help_text=_("the feature type object which is described by this capabilities "
                                                    "document."))
    service_metadata = models.OneToOneField(to=ServiceMetadata,
                                            on_delete=models.CASCADE,
                                            null=True,
                                            blank=True,
                                            related_name="document",
                                            related_query_name="document",
                                            verbose_name=_("related dataset metadata"),
                                            help_text=HELP_TEXT)
    layer_metadata = models.OneToOneField(to=LayerMetadata,
                                          on_delete=models.CASCADE,
                                          null=True,
                                          blank=True,
                                          related_name="document",
                                          related_query_name="document",
                                          verbose_name=_("related layer metadata"),
                                          help_text=HELP_TEXT)
    feature_type_metadata = models.OneToOneField(to=FeatureTypeMetadata,
                                                 on_delete=models.CASCADE,
                                                 null=True,
                                                 blank=True,
                                                 related_name="document",
                                                 related_query_name="document",
                                                 verbose_name=_("related feature type metadata"),
                                                 help_text=HELP_TEXT)
    dataset_metadata = models.OneToOneField(to=DatasetMetadata,
                                            on_delete=models.CASCADE,
                                            null=True,
                                            blank=True,
                                            related_name="document",
                                            related_query_name="document",
                                            verbose_name=_("related dataset metadata"),
                                            help_text=HELP_TEXT)
    xml = models.FileField(verbose_name=_("xml"),
                           help_text=_("the currently actual xml (original or edited content)."))
    xml_backup = models.FileField(verbose_name=_("xml backup"),
                                  help_text=_("the original xml as backup to restore the xml field."))

    class Meta:
        # One Metadata/Service object can be related to multiple Document objects, cause we save the original and the
        # customized version of a given xml.
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_one_related_object_selected",
                # FIXME: fix constraints to match the case, that only one of the OneToOneFields above shall be set while
                #  all other OneToOneFields are Null.
                check=Q(
                    (Q(service=False,
                       service_metadata=False,
                       layer_metadata=False,
                       feature_type_metadata=False,
                       dataset_metadata=False) |
                     Q(service=True,
                       service_metadata=False,
                       layer_metadata=False,
                       feature_type_metadata=False,
                       dataset_metadata=False) |
                     Q(service=False,
                       service_metadata=True,
                       layer_metadata=False,
                       feature_type_metadata=False,
                       dataset_metadata=False) |
                     Q(service=False,
                       service_metadata=False,
                       layer_metadata=True,
                       feature_type_metadata=False,
                       dataset_metadata=False) |
                     Q(service=False,
                       service_metadata=False,
                       layer_metadata=False,
                       feature_type_metadata=True,
                       dataset_metadata=False) |
                     Q(service=False,
                       service_metadata=False,
                       layer_metadata=False,
                       feature_type_metadata=False,
                       dataset_metadata=True))
                    and ~Q(Q(service=True)
                           and Q(service_metadata=True)
                           and Q(layer_metadata=True)
                           and Q(feature_type_metadata=True)
                           and Q(dataset_metadata=True))
                    and ~Q(Q(service=False)
                           and Q(service_metadata=False)
                           and Q(layer_metadata=False)
                           and Q(feature_type_metadata=False)
                           and Q(dataset_metadata=False))
                )
            ),
        ]

    def __str__(self):
        return f"{self.related_object_id} ({self.document_type.value})"

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.xml_backup = self.xml
        super().save(*args, **kwargs)

    def clean(self):
        """ Raise ValidationError if service metadata, layer metadata, feature type metadata and dataset metadata are
            selected OR if none of them are selected.
        """
        msg = _("multiple or empty selections for related objects are not supported. Select only one of service "
                "metadata or a layer metadata or a feature type metadata or a dataset metadata.")
        # FIXME: fix constraints to match the case, that only one of the OneToOneFields above shall be set while
        #  all other OneToOneFields are Null.
        supported_conditions = [(self.service
                                 and not self.service_metadata
                                 and not self.layer_metadata
                                 and not self.feature_type_metadata
                                 and not self.dataset_metadata),
                                (not self.service
                                 and self.service_metadata
                                 and not self.layer_metadata
                                 and not self.feature_type_metadata
                                 and not self.dataset_metadata),
                                (not self.service
                                 and not self.service_metadata
                                 and self.layer_metadata
                                 and not self.feature_type_metadata
                                 and not self.dataset_metadata),
                                (not self.service
                                 and not self.service_metadata
                                 and not self.layer_metadata
                                 and self.feature_type_metadata
                                 and not self.dataset_metadata),
                                (not self.service
                                 and not self.service_metadata
                                 and not self.layer_metadata
                                 and not self.feature_type_metadata
                                 and self.dataset_metadata)]
        for supported_condition in supported_conditions:
            if supported_condition:
                return
        raise ValidationError(msg)

    @property
    def related_object(self):
        if self.service_id:
            return self.service
        elif self.layer_id:
            return self.layer
        elif self.feature_type_id:
            return self.feature_type
        elif self.service_metadata_id:
            return self.service_metadata
        elif self.layer_metadata_id:
            return self.layer_metadata
        elif self.feature_type_metadata_id:
            return self.feature_type_metadata
        elif self.dataset_metadata_id:
            return self.dataset_metadata

    @property
    def related_object_id(self):
        if self.service_id:
            return self.service_id
        elif self.layer_id:
            return self.layer_id
        elif self.feature_type_id:
            return self.feature_type_id
        elif self.service_metadata_id:
            return self.service_metadata_id
        elif self.layer_metadata_id:
            return self.layer_metadata_id
        elif self.feature_type_metadata_id:
            return self.feature_type_metadata_id
        elif self.dataset_metadata_id:
            return self.dataset_metadata_id

    @property
    def document_type(self) -> DocumentEnum:
        if self.service_id or self.layer_id or self.feature_type_id:
            return DocumentEnum.CAPABILITY
        elif self.service_metadata_id or self.layer_metadata_id or \
                self.feature_type_metadata_id or self.dataset_metadata_id:
            return DocumentEnum.METADATA

    def _get_parsed_object(self, get_original: bool = False):
        xml = self.xml if get_original else self.xml_backup
        xml = bytes(xml, "utf-8")
        if self.document_type == DocumentEnum.METADATA:
            parsed_metadata = xmlmap.load_xmlobject_from_string(string=xml,
                                                                xmlclass=WrappedIsoMetadata)
            return parsed_metadata.iso_metadata[0]
        else:
            return get_parsed_service(xml=xml)

    def restore(self):
        self.xml = self.xml_backup
        self.save()
        return self, self._get_parsed_object(get_original=True)

    def update_xml_content(self):
        parsed_metadata = self._get_parsed_object()
        parsed_metadata.update_fields(**self.related_object.get_field_dict())
        self.xml = str(parsed_metadata.serializeDocument(), "UTF-8")
        self.save()

    def camouflaged(self, request: HttpRequest) -> str:
        """Camouflage all urls which are founded in current xml from the xml attribute on-the-fly with the hostname
        from the given request.

        :return: the secured xml
        :rtype: str
        """

        path = reverse("resourceNew:service_operation_view", args=[self.service_id])
        new_url = f"{request.scheme}://{request.get_host()}{path}?"
        if self.document_type == DocumentEnum.METADATA:
            # todo
            return self.xml
        else:
            xml_service = self._get_parsed_object()
            # todo: camouflage metadata urls also
            for operation_url in xml_service.operation_urls:
                operation_url.url = new_url
            if xml_service.url:
                xml_service.url.url = new_url
            if hasattr(xml_service, "get_all_layers"):
                for layer in xml_service.get_all_layers():
                    for style in layer.styles:
                        style.legend_url.legend_url.url = f"{new_url}{style.legend_url.legend_url.url.split('?', 1)[-1]}"
            # todo: only support xml Exception format --> remove all others
            return xml_service.serializeDocument()
