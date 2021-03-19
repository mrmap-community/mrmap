"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 17.03.21

"""
from enum import Enum


class RoleNameEnum(Enum):
    GROUP_ADMIN = "group_admin"
    ORGANIZATION_ADMIN = "organization_admin"
    EDITOR_ADMIN = "editor_admin"
    CONTROLLER_ADMIN = "controller_admin"
    RESOURCE_ADMIN = "resource_admin"


class PermissionEnum(Enum):
    """Holds possible permissions as enums"""
    CAN_CREATE_ORGANIZATION = "structure.add_organization"
    CAN_EDIT_ORGANIZATION = "structure.change_organization"
    CAN_DELETE_ORGANIZATION = "structure.delete_organization"
    CAN_VIEW_ORGANIZATION = "structure.view_organization"

    CAN_CREATE_GROUP = "structure.add_mrmapgroup"
    CAN_DELETE_GROUP = "structure.delete_mrmapgroup"
    CAN_EDIT_GROUP = "structure.change_mrmapgroup"
    CAN_VIEW_GROUP = "structure.view_mrmapgroup"

    CAN_ADD_USER_TO_GROUP = "structure.add_user_to_group"
    CAN_REMOVE_USER_FROM_GROUP = "structure.remove_user_from_group"

    CAN_EDIT_METADATA = "service.change_metadata"
    CAN_VIEW_METADATA = "service.view_metadata"

    CAN_REGISTER_RESOURCE = "service.add_resource"
    CAN_REMOVE_RESOURCE = "service.delete_resource"

    CAN_ACTIVATE_RESOURCE = "service.activate_resource"

    CAN_UPDATE_RESOURCE = "service.update_resource"

    CAN_ADD_DATASET_METADATA = "service.add_dataset_metadata"
    CAN_REMOVE_DATASET_METADATA = "service.delete_dataset_metadata"

    CAN_TOGGLE_PUBLISH_REQUESTS = "structure.toggle_publish_requests"
    CAN_REMOVE_PUBLISHER = "structure.remove_publisher"

    CAN_REQUEST_TO_BECOME_PUBLISHER = "structure.request_to_become_publisher"

    CAN_GENERATE_API_TOKEN = "rest_framework.add_token"
    CAN_HARVEST = "service.harvest_resource"

    CAN_VIEW_PROXY_LOG = "service.view_proxylog"

    CAN_RUN_MONITORING = "monitoring.add_monitoringrun"
    CAN_RUN_VALIDATION = "quality.add_conformitycheckrun"
