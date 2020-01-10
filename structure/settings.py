"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.06.19

"""


# In hours: how long an activation link is valid for a user
USER_ACTIVATION_TIME_WINDOW = 24

# In hours: how long an activation request for publishing is valid
# days * hours/day
PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW = 7 * 24

PENDING_REQUEST_TYPE_PUBLISHING = "publishing"