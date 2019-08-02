"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.07.19


This file holds all messages that are used system-wide
"""
from django.utils.translation import gettext_lazy as _

# GROUP ACTIVITIES #
# These messages HAVE to be untranslated, since they are written into the db
# and will be translated during the template rendering process automatically
PUBLISHING_REQUEST_CREATED  = "Publish request created"
SERVICE_REGISTERED          = "Service registered"
SERVICE_REMOVED             = "Service removed"
SERVICE_UPDATED             = "Service updated"
SERVICE_MD_EDITED           = "Service metadata edited"
SERVICE_ACTIVATED           = "Service activated"
SERVICE_DEACTIVATED         = "Service deactivated"
SERVICE_MD_RESTORED         = "Service metadata restored"
GROUP_EDITED                = "Group edited"

####################

FORM_INPUT_INVALID = _("The input was not valid.")

USERNAME_OR_PW_INVALID = _("Username or password incorrect")
ACCOUNT_UPDATE_SUCCESS = _("Account updated successfully!")
ACCOUNT_NOT_ACTIVATED = _("Your account is currently not activated")
LOGOUT_FORCED = _("You have been logged out.")

ACTIVATION_LINK_INVALID = _("Your activation link was invalid. Please contact an administrator.")
ACTIVATION_LINK_SENT = _("An activation link for your account was sent. Please check your e-mails!")

UNKNOWN_EMAIL = _("This e-mail is not known")
LOGOUT_SUCCESS = _("Successfully logged out!")
EMAIL_INVALID = _("The e-mail address was not valid")

PASSWORD_CHANGE_SUCCESS = _("Password successfully changed!")
PASSWORD_CHANGE_NO_MATCH = _("Passwords didn't match!")
PASSWORD_SENT = _("A new password has been sent. Please check your e-mails!")

SESSION_TIMEOUT = _("Session timeout. You have been logged out.")

NO_PERMISSION = _("You do not have permissions for this!")

METADATA_RESTORING_SUCCESS = _("Metadata restored to original")
METADATA_EDITING_SUCCESS = _("Metadata editing successful")
METADATA_IS_ORIGINAL = _("Metadata is original. No need for restoring anything.")

REQUEST_ACTIVATION_TIMEOVER = _("The request was not activated in time. Request was deleted.")

PUBLISH_REQUEST_SENT = _("Publish request has been sent to the organization!")
PUBLISH_REQUEST_ACCEPTED = _("Publisher request accepted for group '{}'")
PUBLISH_REQUEST_DENIED = _("Publisher request denied for group '{}'")
PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER = _("Your group already is a publisher for this organization!")
PUBLISH_REQUEST_ABORTED_OWN_ORG = _("You cannot be a publisher to your group's own organization! You publish by default like this.")
PUBLISH_REQUEST_ABORTED_IS_PENDING = _("Your group already has sent a request. Please be patient!")

GROUP_CAN_NOT_BE_OWN_PARENT = _("A group can not be parent to itself!")

SERVICE_UPDATE_WRONG_TYPE = _("You tried to update a service to another service type. This is not possible!")
SERVICE_UPDATE_ABORTED_NO_DIFF = _("The provided capabilities document is not different from the currently registered. Update canceled!")
SERVICE_GENERIC_ERROR = _("The service could not be registered. Please check your metadata and contact an administrator.")

EDITOR_INVALID_ISO_LINK = _("'{}' was invalid.")
