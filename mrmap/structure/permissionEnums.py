"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.08.20

"""
from MrMap.enums import EnumChoice


class PermissionEnum(EnumChoice):
    """ Holds possible permissions as enums for all needed model classes project wide.

    """
    # Organization
    CAN_CREATE_ORGANIZATION = "structure.add_organization"
    CAN_EDIT_ORGANIZATION = "structure.change_organization"
    CAN_DELETE_ORGANIZATION = "structure.delete_organization"
    CAN_VIEW_ORGANIZATION = "structure.view_organization"

    # Metadata
    CAN_EDIT_METADATA = "service.change_metadata"
    CAN_VIEW_METADATA = "service.view_metadata"
    # custom Metadata permissions
    CAN_REGISTER_RESOURCE = "service.add_resource"
    CAN_REMOVE_RESOURCE = "service.delete_resource"
    CAN_ACTIVATE_RESOURCE = "service.activate_resource"
    CAN_UPDATE_RESOURCE = "service.update_resource"
    CAN_ADD_DATASET_METADATA = "service.add_dataset_metadata"
    CAN_REMOVE_DATASET_METADATA = "service.delete_dataset_metadata"
    CAN_HARVEST = "service.harvest_resource"
    CAN_SECURE_RESOURCE = "service.secure_resource"

    # PublishRequest
    CAN_VIEW_PUBLISH_REQUEST = "structure.view_publishrequest"
    CAN_ADD_PUBLISH_REQUEST = "structure.add_publishrequest"
    CAN_EDIT_PUBLISH_REQUEST = "structure.change_publishrequest"
    CAN_DELETE_PUBLISH_REQUEST = "structure.delete_publishrequest"

    # PendingTask
    CAN_VIEW_PENDING_TASK = "structure.view_pendingtask"
    CAN_DELETE_PENDING_TASK = "structure.delete_pendingtask"

    # Rest api
    CAN_GENERATE_API_TOKEN = "rest_framework.add_token"

    # ProxyLog
    CAN_VIEW_PROXY_LOG = "service.view_proxylog"

    # MonitoringRun
    CAN_VIEW_MONITORING_RUN = "monitoring.view_monitoringrun"
    CAN_ADD_MONITORING_RUN = "monitoring.add_monitoringrun"

    # MonitoringResult
    CAN_VIEW_MONITORING_RESULT = "monitoring.view_monitoringresult"

    # HealthState
    CAN_VIEW_HEALTH_STATE = "monitoring.view_healthstate"

    # ConformityCheckRun
    CAN_RUN_VALIDATION = "quality.add_conformitycheckrun"

    # Subscription
    CAN_VIEW_SUBSCRIPTION = "users.view_subscription"
    CAN_EDIT_SUBSCRIPTION = "users.edit_subscription"
    CAN_DELETE_SUBSCRIPTION = "users.delete_subscription"

    # AllowedOperation
    CAN_VIEW_ALLOWED_OPERATION = "service.view_allowedoperation"
    CAN_CHANGE_ALLOWED_OPERATION = "service.change_allowedoperation"
    CAN_DELETE_ALLOWED_OPERATION = "service.delete_allowedoperation"
    CAN_ADD_ALLOWED_OPERATION = "service.add_allowedoperation"

