from service.helper.enums import EnumChoice


class HealthStateEnum(EnumChoice):
    """ Defines all pending task types

    """
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
