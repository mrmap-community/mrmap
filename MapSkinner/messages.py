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
PUBLISHING_REQUEST_CREATED = "Publish request created"
SERVICE_REGISTERED = "Service registered"
SERVICE_REMOVED = "Service removed"
SERVICE_UPDATED = "Service updated"
SERVICE_MD_EDITED = "Service metadata edited"
SERVICE_ACTIVATED = "Service activated"
SERVICE_DEACTIVATED = "Service deactivated"
SERVICE_MD_RESTORED = "Service metadata restored"
GROUP_EDITED = "Group edited"

####################

FORM_INPUT_INVALID = _("The input was not valid.")

USERNAME_OR_PW_INVALID = _("Username or password incorrect")
REGISTRATION_FAILED_MISSING_DATA = _("Registration failed due to missing form data.")
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
METADATA_IS_ORIGINAL = _("Metadata is original. Reset aborted.")
METADATA_PROXY_NOT_POSSIBLE_DUE_TO_SECURED = _("You have to turn off the secured access before you can turn off the proxy.")


MISSING_DATASET_ID_IN_METADATA = _("No datasetId found in metadata!")

REQUEST_ACTIVATION_TIMEOVER = _("The request was not activated in time. Request was deleted.")

PUBLISH_REQUEST_SENT = _("Publish request has been sent to the organization!")
PUBLISH_REQUEST_ACCEPTED = _("Publisher request accepted for group '{}'")
PUBLISH_REQUEST_DENIED = _("Publisher request denied for group '{}'")
PUBLISH_REQUEST_ABORTED_ALREADY_PUBLISHER = _("Your group already is a publisher for this organization!")
PUBLISH_REQUEST_ABORTED_OWN_ORG = _("You cannot be a publisher to your group's own organization! You publish by default like this.")
PUBLISH_REQUEST_ABORTED_IS_PENDING = _("Your group already has sent a request. Please be patient!")

PUBLISH_PERMISSION_REMOVED = _("Publishing permission of {} for {} removed.")
PUBLISH_PERMISSION_REMOVING_DENIED = _("Publish permission removing denied. You are not a member of the organization nor a member of the publishing group!")

GROUP_CAN_NOT_BE_OWN_PARENT = _("A group can not be parent to itself!")
GROUP_IS_OTHERS_PROPERTY = _("This group is owned by another user. Action denied.")
GROUP_FORM_INVALID = _("The form data was not valid.")
ORGANIZATION_FORM_INVALID = GROUP_FORM_INVALID
ORGANIZATION_CAN_NOT_BE_OWN_PARENT = _("An organization can not be parent to itself!")
ORGANIZATION_IS_OTHERS_PROPERTY = _("This organization is owned by another user. Action denied.")

SERVICE_REGISTRATION_ABORTED = _("The service registration for '{}' was canceled")
SERVICE_REGISTRATION_TIMEOUT = _("Timeout while loading '{}'!")
SERVICE_UPDATE_WRONG_TYPE = _("You tried to update a service to another service type. This is not possible!")
SERVICE_UPDATE_ABORTED_NO_DIFF = _("The provided capabilities document is not different from the currently registered. Update canceled!")
SERVICE_GENERIC_ERROR = _("The service could not be registered. Please check your metadata and contact an administrator.")
SERVICE_LAYER_NOT_FOUND = _("The requested layer could not be found.")
SERVICE_NOT_FOUND = _("The requested service could not be found.")
SERVICE_DISABLED = _("423 - The requested resource is currently disabled.")

SECURITY_PROXY_ERROR_MULTIPLE_SECURED_OPERATIONS = _("There are multiple secured operations for one metadata. Please contact an administator.")
SECURITY_PROXY_NOT_ALLOWED = _("You have no permission to access this resource.")
SECURITY_PROXY_MUST_BE_ENABLED_FOR_LOGGING = _("Proxy must be activated to be logged!")
SECURITY_PROXY_MUST_BE_ENABLED_FOR_SECURED_ACCESS = _("Proxy must be enabled if service shall stay secured!")
SECURITY_PROXY_ERROR_OPERATION_NOT_SUPPORTED = _("The requested operation is not supported by this resource.")
SECURITY_PROXY_ERROR_BROKEN_URI = _("The requested uri seems to be broken. Please inform an administrator.")
SECURITY_PROXY_ERROR_PARAMETER = _("The following parameter seems to be invalid. Please check '{}'.")
SECURITY_PROXY_ERROR_MISSING_REQUEST_TYPE = _("No 'request' parameter provided.")
SECURITY_PROXY_ERROR_MISSING_EXT_AUTH_KEY = _("Login credentials for external authentication could not be decrypted. The key is missing. Please inform an administrator.")
SECURITY_PROXY_ERROR_WRONG_EXT_AUTH_KEY = _("Login credentials for external authentication could not be decrypted. The key is wrong. Please inform an administrator.")

MULTIPLE_SERVICE_METADATA_FOUND = _("There are several service metadata documents for this service. Please contact an administrator.")

EDITOR_INVALID_ISO_LINK = _("'{}' was invalid.")
EDITOR_ACCESS_RESTRICTED = _("Access for '{}' changed successfully.")

TD_POINT_HAS_NOT_ENOUGH_VALUES = _("2D-Points must hold two values for x and y.")  # TD_ = 2D_