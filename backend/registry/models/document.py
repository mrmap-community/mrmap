from abc import abstractmethod
from warnings import warn

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from eulxml import xmlmap
from eulxml.xmlmap import XmlObject
from ows_lib.xml_mapper.capabilities.mixins import OGCServiceMixin
from ows_lib.xml_mapper.utils import get_parsed_service
from registry.mapping.capabilities.utils import get_mapper_for_service


def xml_backup_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'xml_documents/{0}/{1}'.format(instance.pk, filename)


class DocumentModelMixin(models.Model):
    """Abstract model to store documents such as capabilities or ISO MD_Metadata xml for different related objects.

    :attr xml_backup: the original xml as backup to restore the xml fields.
    """
    xml_mapper_cls = None
    xml_backup_file = models.FileField(verbose_name=_("xml backup"),
                                       help_text=_(
                                           "the original xml as backup to restore the xml field."),
                                       upload_to=xml_backup_file_path,
                                       editable=False,
                                       )

    class Meta:
        abstract = True

    def get_xml_mapper_cls(self):
        """Return the configured xml_mapper_cls attribute.

        :raises ImproperlyConfigured: if the concrete model does not configure the xml_mapper_cls attribute.
        """
        warn("get_xml_mapper_cls is deprecated. use utility functions of ows_lib package in stead.")
        if self.xml_mapper_cls:
            return self.xml_mapper_cls
        raise ImproperlyConfigured("xml_mapper_cls attribute is needed.")

    @property
    def xml_backup_string(self) -> str:
        """Return the xml backup file as string

        :return xml_backup: the xml_backup_file as string or empty string if FileNotFound
        :rtype: str
        """
        try:
            with open(self.xml_backup_file.path, "r") as file:
                string = file.read()
            return string if isinstance(string, str) else string.decode("UTF-8")
        except ValueError:
            return ""

    @property
    def xml_backup(self) -> XmlObject:
        """Return the backup xml as XmlObject.

        :return xml_object: the xml mapper object
        :rtype: :class:`xmlmap.XmlObject`
        """
        return xmlmap.load_xmlobject_from_string(string=self.xml_backup_string.encode("UTF-8"),
                                                 xmlclass=self.get_xml_mapper_cls())

    @abstractmethod
    def xml_secured(self, request: HttpRequest) -> XmlObject:
        """Camouflage all urls which are founded in current xml from the xml property on-the-fly with the hostname
        from the given request.

        :return: the secured xml
        :rtype: :class:`xmlmap.XmlObject`
        :raises NotImplementedError: if the concrete model does not implement the method.
        """
        raise NotImplementedError


class CapabilitiesDocumentModelMixin(DocumentModelMixin):

    class Meta:
        abstract = True

    @property
    def xml_backup(self) -> OGCServiceMixin:
        return get_parsed_service(self.xml_backup_string.encode("UTF-8"))

    @property
    def updated_capabilitites(self) -> XmlObject:
        """Returns the current version of the capabilities document.

            The values from the database overwrites the values inside the xml document.
        """
        mapper_cls = get_mapper_for_service(self)
        mapper = mapper_cls(source_obj=self)
        xml_object = mapper.update(destination_obj=self.xml_backup)
        return xml_object

    def xml_secured(self, request: HttpRequest) -> str:
        path = reverse("wms-operation", args=[self.pk])
        new_url = f"{request.scheme}://{request.get_host()}{path}?"

        capabilities_xml = self.updated_capabilitites
        # TODO: camouflage metadata urls also
        for operation_url in capabilities_xml.operation_urls:
            operation_url.url = new_url
        if capabilities_xml.service_url:
            capabilities_xml.service_url = new_url

        for layer in capabilities_xml.layers:
            for style in layer.styles:
                style.legend_url.legend_url.url = f"{new_url}{style.legend_url.legend_url.url.split('?', 1)[-1]}"
        # TODO: only support xml Exception format --> remove all others
        return capabilities_xml.serializeDocument()

    def get_capabilitites_for_request(self, request: HttpRequest) -> str:
        """Returns the current version of the capabilities document.

            The values from the database overwrites the values inside the xml document.
        """
        if self.camouflage:
            return self.xml_secured(request=request)
        else:
            return self.updated_capabilitites.serializeDocument()


class MetadataDocumentModelMixin(DocumentModelMixin):

    class Meta:
        abstract = True

    def restore(self):
        """Restore the current model instance from the xml_backup file

        :raises NotImplementedError: if the concrete model does not implement the method.
        """
        # todo: restore_dict = self.xml().get_field_dict()
        raise NotImplementedError

    def xml_secured(self, request: HttpRequest) -> XmlObject:
        # todo
        return self.xml
