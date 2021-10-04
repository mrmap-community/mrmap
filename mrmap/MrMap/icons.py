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


    # TODO: change to boostrap icons


    PROXY = "fas fa-archway"
    LOGGING = "fas fa-file-signature"
    
    CSW = "fas fa-book"
    DATASET = "fas fa-clipboard-list"
    MAP_CONTEXT = "fas fa-map-marked-alt"
    HEARTBEAT = "fas fa-heartbeat"
    PENDING_TASKS = "fas fa-tasks"
    INFO = "fas fa-info"
    NEWSPAPER = "far fa-newspaper"
    METADATA = "fas fa-file-alt"


    LOGS = "fas fa-stethoscope"
    PUBLIC = "fas fa-globe"
    
    PUBLISHERS = "fas fa-address-card"
    
    
    MONITORING_RUN = "fas fa-running"
    MONITORING_RESULTS = "fas fa-poll-h"
    HEALTH_STATE = "fas fa-heartbeat"

    UPDATE = 'fas fa-spinner'
    RESTORE = 'fas fa-undo'
    HARVEST = 'fas fa-level-down-alt'
    WINDOW_CLOSE = 'fas fa-window-close'
    WMS_SOLID = 'fas fa-map'
    PENDINGTASKS = 'fas fa-tasks'
    REMOVE = 'fas fa-trash'
    RETURN = 'fas fa-arrow-circle-left'

    VALIDATION = 'fas fa-check-circle'
    VALIDATION_ERROR = 'fas fa-times-circle'
    VALIDATION_UNKNOWN = 'fas', 'fa-question-circle'

    SORT_ALPHA_UP = 'fas fa-sort-alpha-up'
    SORT_ALPHA_DOWN = 'fas fa-sort-alpha-down'


    ACTIVITY = 'fas fa-snowboarding'
    HISTORY = 'fas fa-history'
    UPLOAD = 'fas fa-upload'
    SEND_EMAIL = 'fas fa-envelope-open-text'
    GLOBE = 'fas fa-globe'
    LINK = 'fas fa-link'
    EXTERNAL_LINK = 'fas fa-external-link-alt'
    PUBLISHER = 'fas fa-address-card'
    HOME = 'fas fa-home'
    API = 'fas fa-hashtag'
    CSV = 'fas fa-file-csv'
    FILTER = 'fas fa-filter'
    FIRST = 'fas fa-fast-backward'
    BACK = 'fas fa-step-backward'
    NEXT = 'fas fa-step-forward'
    LAST = 'fas fa-fast-forward'
    BRAIN = 'fas fa-brain'
    EYE = 'fas fa-eye'
    SETTINGS = 'fas fa-cogs'
    RESOURCE = 'fas fa-database'
    ON = 'fas fa-toggle-on'
    OFF = 'fas fa-toggle-off'
    LIST = 'fas fa-th-list'
    
    CODE = "fas fa-code"
    PENDING = 'fas fa-ellipsis-h'
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
