from django.db import models, OperationalError
from django.utils.translation import gettext_lazy as _


class LicenceManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def as_choices(self) -> list:
        """ Returns a list of (identifier, name) to be used as choices in a form

        Returns:
             tuple_list (list): As described above
        """
        return [(licence.identifier, licence.__str__()) for licence in self.get_queryset().filter(is_active=True)]

    def get_descriptions_help_text(self):
        """ Returns a string containing all Licence records for rendering as help_text in a form

        Returns:
             string (str): As described above
        """
        from django.db.utils import ProgrammingError

        try:
            descrs = [
                "<a href='{}' target='_blank'>{}</a>".format(
                    licence.description_url, licence.identifier
                ) for licence in self.get_queryset().all()
            ]
            descr_str = "<br>".join(descrs)
            descr_str = _("Explanations: <br>") + descr_str
        except (ProgrammingError, OperationalError):
            # This will happen on an initial installation. The Licence table won't be created yet, but this function
            # will be called on makemigrations.
            descr_str = ""
        return descr_str
