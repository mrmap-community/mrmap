from abc import abstractmethod

from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from lxml import etree
from registry.mappers.factory import OGCServiceXmlMapper


def xml_backup_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<id>/<filename>
    return 'xml_documents/{0}/{1}'.format(instance.pk, filename)


class DocumentModelMixin(models.Model):
    """Abstract model to store documents such as capabilities or ISO MD_Metadata xml for different related objects.

    :attr xml_backup: the original xml as backup to restore the xml fields.
    """
    xml_backup_file = models.FileField(verbose_name=_("xml backup"),
                                       help_text=_(
                                           "the original xml as backup to restore the xml field."),
                                       upload_to=xml_backup_file_path,
                                       editable=False,
                                       )

    class Meta:
        abstract = True

    @property
    def xml_backup(self) -> bytes:
        """Return the backup xml as XmlObject.

        :return xml_object: the xml mapper object
        :rtype: :class:`xmlmap.XmlObject`
        """
        try:
            with open(self.xml_backup_file.path, "rb") as file:
                string = file.read()
            return string
        except ValueError:
            return b""

    @property
    def xml_backup_string(self) -> str:
        """Return the xml backup file as string

        :return xml_backup: the xml_backup_file as string or empty string if FileNotFound
        :rtype: str
        """
        return self.xml_backup.decode("UTF-8")

    @abstractmethod
    def xml_secured(self, request: HttpRequest):
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

    def get_updated_capabilitites(self, instance=None) -> etree.ElementTree:
        """Returns the current version of the capabilities document.

            The values from the database overwrites the values inside the xml document.
        """
        return OGCServiceXmlMapper.to_xml(instance or self)

    def get_secured_url(self, request: HttpRequest, url_name: str, kwargs: dict) -> str:
        """Generate a secured url for the given url name and kwargs.

        :param request: the http request
        :type request: HttpRequest
        :param url_name: the name of the url
        :type url_name: str
        :param kwargs: the kwargs for the url
        :type kwargs: dict
        :return: the secured url
        :rtype: str
        """
        path = reverse(url_name, args=[self.pk])
        return f"{request.scheme}://{request.get_host()}{path}?"

    def get_capabilitites_for_request(self, request: HttpRequest) -> str:
        """Returns the current version of the capabilities document.

            The values from the database overwrites the values inside the xml document.
        """
        if self.camouflage:
            return self.xml_secured(request=request)
        else:
            return etree.tostring(
                self.get_updated_capabilitites().getroottree().getroot(),
                pretty_print=True,
                xml_declaration=True,
                encoding="UTF-8"
            )


class MetadataDocumentModelMixin(DocumentModelMixin):

    class Meta:
        abstract = True

    def restore(self):
        """Restore the current model instance from the xml_backup file

        :raises NotImplementedError: if the concrete model does not implement the method.
        """
        # todo: restore_dict = self.xml().get_field_dict()
        raise NotImplementedError

    def xml_secured(self, request: HttpRequest):
        # TODO: implement camouflage for metadata xml
        return self.xml_backup_string
