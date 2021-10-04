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


    # actions
    ADD = "bi bi-plus-circle"
    DELETE = "bi bi-trash"
    EDIT = "bi bi-pen"
    SAVE = 'bi bi-save'
    SEARCH = 'bi bi-search'
    UNDO = 'bi bi-arrow-counterclockwise'

    USER_ADD = "bi bi-person-plus"
    USER_REMOVE = "bi bi-person-x"

    SIGIN = "bi bi-box-arrow-in-right"
    SIGNOUT = "bi bi-box-arrow-right"
    SIGNUP = "bi bi-person-plus"
    DOWNLOAD = "bi bi-download"
    PLAY = "bi bi-play-fill"

    UPDATE = 'bi bi-gear-wide-connected'

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

    BOOK_OPEN = 'bi bi-book-fill'


    NONE = ''

    # wizard
    FIRST = 'bi bi-chevron-bar-left'
    BACK = 'bi bi-chevron-compact-left'
    NEXT = 'bi bi-chevron-compact-right'
    LAST = 'bi bi-chevron-bar-right'

    # etc
    NEWSPAPER = "bi bi-newspaper"
    CODE = "bi bi-code-square"
    PENDING = 'bi bi-three-dots'
    LINK = 'bi bi-link'
    HISTORY = 'bi bi-clock-history'
    GLOBE = 'bi bi-globe'
    HOME = 'bi bi-house-fill'


    # TODO: change to boostrap icons


    PROXY = "fas fa-archway"
    LOGGING = "fas fa-file-signature"
    
    CSW = "fas fa-book"
    DATASET = "fas fa-clipboard-list"
    MAP_CONTEXT = "fas fa-map-marked-alt"
    HEARTBEAT = "fas fa-heartbeat"
    PENDING_TASKS = "fas fa-tasks"
    INFO = "fas fa-info"


    LOGS = "fas fa-stethoscope"
    
    PUBLISHERS = "fas fa-address-card"
    
    
    MONITORING_RUN = "fas fa-running"
    MONITORING_RESULTS = "fas fa-poll-h"
    HEALTH_STATE = "fas fa-heartbeat"

    HARVEST = 'fas fa-level-down-alt'

    PUBLISHER = 'fas fa-address-card'
        
    EXTERNAL_AUTHENTICATION = 'fas fa-user-lock'
    ALLOWED_OPERATION = 'fas fa-lock'
    ACCESS_CONTROL_LIST = "fas fa-user-shield"
    PROXY_SETTING = "fas fa-archway"


def get_icon(enum: IconEnum, color=None) -> SafeString:
    icon = f"<i class=\"{enum.value} {color}\"></i>" if color else f"<i class=\"{enum.value}\"></i>"
    return format_html(icon)


def get_all_icons() -> dict:
    icons = {}
    # if we do not iterate over __members__, duplicate enum values will be ignored.
    for name, enum in IconEnum.__members__.items():
        icons.update({name: get_icon(enum)})
    return icons
