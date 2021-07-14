from abc import ABC, abstractmethod


class PlainObject(ABC):

    @abstractmethod
    def to_db_model(self, *args, **kwargs):
        """ Convert the current plain python object to the concrete django db model without saving it.

        Returns:
             the django db model instance unsaved.
        """
        raise NotImplementedError('You have to implement to_db_model()')

    @abstractmethod
    def to_db(self, *args, **kwargs):
        """ Write the generate

        """
        raise NotImplementedError('You have to implement to_db()')
