from MrMap.enums import EnumChoice


class PendingTaskEnum(EnumChoice):
    PENDING = 'pending'
    STARTED = 'started'
    SUCCESS = 'success'
    FAILURE = 'failure'
