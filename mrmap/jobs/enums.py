from MrMap.enums import EnumChoice


class TaskStatusEnum(EnumChoice):
    PENDING = 'pending'
    STARTED = 'started'
    SUCCESS = 'success'
    FAILURE = 'failure'
