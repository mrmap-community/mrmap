"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.08.20

"""
from service.helper.enums import EnumChoice


class PermissionEnum(EnumChoice):
    """ Holds possible permissions as enums

    """
    CAN_CREATE_ORGANIZATION = "can_create_organization"
    CAN_EDIT_ORGANIZATION = "can_edit_organization"
    CAN_DELETE_ORGANIZATION = "can_delete_organization"

    CAN_CREATE_GROUP = "can_create_group"
    CAN_DELETE_GROUP = "can_delete_group"
    CAN_EDIT_GROUP = "can_edit_group"
    CAN_ADD_USER_TO_GROUP = "can_add_user_to_group"
    CAN_REMOVE_USER_FROM_GROUP = "can_remove_user_from_group"

    CAN_EDIT_GROUP_ROLE = "can_edit_group_role"
    CAN_EDIT_METADATA = "can_edit_metadata"
    CAN_ACTIVATE_RESOURCE = "can_activate_resource"
    CAN_UPDATE_RESOURCE = "can_update_resource"
    CAN_REGISTER_RESOURCE = "can_register_resource"
    CAN_REMOVE_RESOURCE = "can_remove_resource"
    CAN_ADD_DATASET_METADATA = "can_add_dataset_metadata"
    CAN_REMOVE_DATASET_METADATA = "can_remove_dataset_metadata"
    CAN_TOGGLE_PUBLISH_REQUESTS = "can_toggle_publish_requests"
    CAN_REMOVE_PUBLISHER = "can_remove_publisher"
    CAN_REQUEST_TO_BECOME_PUBLISHER = "can_request_to_become_publisher"
    CAN_GENERATE_API_TOKEN = "can_generate_api_token"
    CAN_HARVEST = "can_harvest"
    CAN_ACCESS_LOGS = "can_access_logs"
    CAN_DOWNLOAD_LOGS = "can_download_logs"
    CAN_RUN_MONITORING = "can_run_monitoring"
