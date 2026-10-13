from django.utils.translation import gettext_lazy as _
from registry.enums.alerts import ServiceAlertCategory, ServiceAlertSeverity
from rest_framework.fields import (CharField, ChoiceField, DateTimeField,
                                   SerializerMethodField)
from rest_framework_json_api.serializers import Serializer


class ServiceAlertSerializer(Serializer):
    """ Endpoint answers the states of one service which need attention

        list:
            Retrieves what an administrator has to do about the service which
            the request addresses
    """
    # the id of an alert names the category and the row it was derived from, so
    # that a client recognises the alert while the state behind it changes - it
    # is not a primary key an endpoint of its own is asked for
    id = CharField(
        label=_("id"),
        help_text=_("the category and the id of the row this alert is derived "
                    "from"),
    )
    severity = ChoiceField(
        choices=ServiceAlertSeverity.choices,
        label=_("severity"),
        help_text=_("how much attention the service needs"),
    )
    category = ChoiceField(
        choices=ServiceAlertCategory.choices,
        label=_("category"),
        help_text=_("the state of the service which needs attention"),
    )
    message = CharField(
        label=_("message"),
        help_text=_("why this service needs attention"),
    )
    service = SerializerMethodField(
        label=_("service"),
        help_text=_("the reported service, addressed by its type and id"))
    service_title = CharField(
        label=_("service title"),
        help_text=_("the title of the reported service"),
    )
    resource = SerializerMethodField(
        label=_("resource"),
        help_text=_("the run or job which carries the problem, addressed by "
                    "its type and id"))
    occurred_at = DateTimeField(
        allow_null=True,
        label=_("occurred at"),
        help_text=_("when the reported state appeared"),
    )

    def get_service(self, alert) -> dict:
        """Address the service which this alert reports about.

        Args:
            alert (dict): the alert which was collected for the service

        Returns:
            dict: the type and the id to ask the service for, like the related
                resource of a background process is answered
        """
        return {"type": alert["service_type"], "id": alert["service"]}

    def get_resource(self, alert) -> dict:
        """Address the row which this alert was derived from.

        Args:
            alert (dict): the alert which was collected for the service

        Returns:
            dict: the type and the id of the run or job behind the alert, which
                is the resource an administrator has to decide about
        """
        return {"type": alert["resource_type"], "id": alert["resource_id"]}

    class Meta:
        resource_name = 'ServiceAlert'
