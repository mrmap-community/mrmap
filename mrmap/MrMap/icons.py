from django.utils.html import format_html
from django.utils.safestring import SafeString
from MrMap.enums import EnumChoice


class IconEnum(EnumChoice):
    POWER_OFF = "bi bi-power"
    
    # models
    USER = 'bi bi-person'
    GROUP = 'bi bi-people'
    ORGANIZATION = "bi bi-building"

    WMS = "bi bi-map"
    LAYER = "bi bi-layers-half"

    WFS = "bi bi-bounding-box-circles"
    FEATURETYPE = "bi bi-bounding-box-circles"

    CSW = "bi bi-journal-code"

    CAPABILITIES = "bi bi-file-earmark-code"
    PASSWORD = "bi bi-lock"
    ACCESS = "bi bi-key"
    SUBSCRIPTION = "bi bi-megaphone-fill"

    MONITORING = "bi bi-binoculars-fill"
    HIERARCHY = 'bi bi-diagram-3-fill'

    DASHBOARD = 'bi bi-speedometer2'
    RESOURCE = 'bi bi-hdd-stack'
    METADATA = "bi bi-file-text-fill"
    VALIDATION = 'bi bi-ui-checks'

    PENDING_TASKS = "bi bi-list-task"

    PUBLISHER = "bi bi-person-badge-fill"
    PUBLISHERS = PUBLISHER

    ALLOWED_OPERATION = 'bi bi-shield-fill-check'
    ACCESS_CONTROL_LIST = "bi bi-shield-lock-fill"
    EXTERNAL_AUTHENTICATION = 'bi bi-file-lock2'
    PROXY_SETTING = "bi bi-gear-fill"
    HEARTBEAT = "bi bi-heart-half"
    DATASET = "bi bi-file-earmark-text"
    LOGS = "bi bi-file-earmark-medical-fill"
    LOGGING = "bi bi-chat-text"

    MAP_CONTEXT = "bi bi-pin-map-fill"
    PROXY = "bi bi-distribute-vertical"

    # actions
    ADD = "bi bi-plus-circle"
    DELETE = "bi bi-trash"
    EDIT = "bi bi-pen"
    SAVE = 'bi bi-save'
    SEARCH = 'bi bi-search'
    UNDO = 'bi bi-arrow-counterclockwise'

    USER_ADD = "bi bi-person-plus"
    USER_REMOVE = "bi bi-person-x"

    SIGNIN = "bi bi-box-arrow-in-right"
    SIGNOUT = "bi bi-box-arrow-right"
    SIGNUP = "bi bi-person-plus"
    DOWNLOAD = "bi bi-download"
    PLAY = "bi bi-play-fill"

    UPDATE = 'bi bi-gear-wide-connected'
    HARVEST = 'bi bi-cloud-download'

    SORT_ASC = "bi bi-sort-alpha-down"
    SORT_DESC = "bi bi-sort-alpha-up"

    # states
    OK = "bi bi-hand-thumbs-up-fill"
    NOK = "bi bi-hand-thumbs-down-fill"
    OK_CIRCLE = 'bi bi-check-circle'
    NOK_CIRCLE = 'bi bi-x-circle'
    WARNING = 'bi bi-exclamation-triangle-fill'
    CRITICAL = 'bi bi-lightning-fill'
    ERROR = "bi bi-bug-fill"
    PENDING = 'bi bi-hourglass'

    # wizard
    FIRST = 'bi bi-chevron-bar-left'
    BACK = 'bi bi-chevron-compact-left'
    NEXT = 'bi bi-chevron-compact-right'
    LAST = 'bi bi-chevron-bar-right'

    # etc
    NEWSPAPER = "bi bi-newspaper"
    CODE = "bi bi-code-square"
    LINK = 'bi bi-link'
    HISTORY = 'bi bi-clock-history'
    GLOBE = 'bi bi-globe'
    HOME = 'bi bi-house-fill'
    BOOK_OPEN = 'bi bi-book-fill'
    NONE = ''
   

def get_icon(enum: IconEnum, color=None) -> SafeString:
    icon = f"<i class=\"{enum.value} {color}\"></i>" if color else f"<i class=\"{enum.value}\"></i>"
    return format_html(icon)


def get_all_icons() -> dict:
    icons = {}
    # if we do not iterate over __members__, duplicate enum values will be ignored.
    for name, enum in IconEnum.__members__.items():
        icons.update({name: get_icon(enum)})
    return icons
