from service.helper.enums import EnumChoice


class HealthStateEnum(EnumChoice):
    """ Defines all HealthState status types

    """
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    UNAUTHORIZED = "unauthorized"
