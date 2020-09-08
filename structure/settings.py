"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.06.19

"""
import logging
from django.utils.translation import gettext_lazy as _

structure_logger = logging.getLogger('MrMap.structure')

# In hours: how long an activation link is valid for a user
USER_ACTIVATION_TIME_WINDOW = 24

# In hours: how long an activation request for publishing is valid
# days * hours/day
PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW = 7 * 24
GROUP_INVITATION_REQUEST_ACTIVATION_TIME_WINDOW = 7 * 24

SUPERUSER_ROLE_NAME = _("Administrator")
SUPERUSER_GROUP_NAME = _("Administrator")
SUPERUSER_GROUP_DESCRIPTION = _("Permission group. Holds user which are allowed to perform any action.")
PUBLIC_ROLE_NAME = _("public_role")
PUBLIC_GROUP_NAME = _("Public")
PUBLIC_GROUP_DESCRIPTION = _("The public group. Used to create access for secured resources to external users. Every user is member of this group by default.")
