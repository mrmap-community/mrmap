"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
import logging
from django.utils.translation import gettext_lazy as _

quality_logger = logging.getLogger('MrMap.quality')

# Some pre defined quality messages
DEFAULT_UNKNOWN_MESSAGE = _(f'The validation state is unknown.')
DEFAULT_SUCCESS_MESSAGE = _(f'The resource is valid.')
DEFAULT_FAIL_MESSAGE = _(f'The resource is invalid.')
