from django.utils.html import format_html
from django.utils.safestring import SafeString
from MrMap.enums import EnumChoice


class IconEnum(EnumChoice):
    POWER_OFF = "fas fa-power-off"
    PROXY = "fas fa-archway"
    LOGGING = "fas fa-file-signature"
    WFS = "fas fa-draw-polygon"
    FEATURETYPE = "fas fa-draw-polygon"
    WMS = "far fa-map"
    LAYER = "fas fa-layer-group"
    CSW = "fas fa-book"
    DATASET = "fas fa-clipboard-list"
    MAP_CONTEXT = "fas fa-map-marked-alt"
    PASSWORD = "fas fa-lock"
    HEARTBEAT = "fas fa-heartbeat"
    PENDING_TASKS = "fas fa-tasks"
    INFO = "fas fa-info"
    CAPABILITIES = "fas fa-file-code"
    NEWSPAPER = "far fa-newspaper"
    METADATA = "fas fa-file-alt"
    ERROR = "fas fa-exclamation-circle"
    PLAY = "fas fa-play"
    LOGS = "fas fa-stethoscope"
    DOWNLOAD = "fas fa-download"
    PUBLIC = "fas fa-globe"
    EDIT = "fas fa-edit"
    ACCESS = "fas fa-key"
    SUBSCRIPTION = "fas fa-bullhorn"
    DELETE = "fas fa-trash"
    GROUP = "fas fa-users"
    SIGNOUT = "fas fa-sign-out-alt"
    PUBLISHERS = "fas fa-address-card"
    ADD = "fas fa-plus-circle"
    OK = "fas fa-check"
    NOK = "fas fa-times"
    ORGANIZATION = "fas fa-building"
    USER = "fas fa-user"
    USER_ADD = "fa fa-user-plus"
    USER_REMOVE = "fa fa-user-times"
    MONITORING = "fas fa-binoculars"
    MONITORING_RUN = "fas fa-running"
    MONITORING_RESULTS = "fas fa-poll-h"
    WARNING = 'fas fa-exclamation-triangle'
    CRITICAL = 'fas fa-bolt'
    UPDATE = 'fas fa-spinner'
    RESTORE = 'fas fa-undo'
    HARVEST = 'fas fa-level-down-alt'
    WINDOW_CLOSE = 'fas fa-window-close'
    DASHBOARD = 'fas fa-tachometer-alt'
    WMS_SOLID = 'fas fa-map'
    PENDINGTASKS = 'fas fa-tasks'
    REMOVE = 'fas fa-trash'
    SEARCH = 'fas fa-search'
    RETURN = 'fas fa-arrow-circle-left'
    OK_CIRCLE = 'far fa-check-circle'
    NOK_CIRCLE = 'far fa-times-circle'
    SIGNIN = 'fas fa-sign-in-alt'
    SIGNUP = 'fas fa-user-plus'
    UNDO = 'fas fa-undo'
    VALIDATION = 'fas fa-check-circle'
    VALIDATION_ERROR = 'fas fa-times-circle'
    VALIDATION_UNKNOWN = 'fas', 'fa-question-circle'
    SORT_ALPHA_UP = 'fas fa-sort-alpha-up'
    SORT_ALPHA_DOWN = 'fas fa-sort-alpha-down'
    ACTIVITY = 'fas fa-snowboarding'
    HISTORY = 'fas fa-history'
    SAVE = 'fas fa-save'
    UPLOAD = 'fas fa-upload'
    SEND_EMAIL = 'fas fa-envelope-open-text'
    HIERARCHY = 'fas fa-sitemap'
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
    NONE = ''
    BOOK = 'fas fa-book'
    CODE = "fas fa-code"
    BOOK_OPEN = 'fas fa-book-open'
    PENDING = 'fas fa-ellipsis-h'
    EXTERNAL_AUTHENTICATION = 'fas fa-user-lock'
    ALLOWED_OPERATION = 'fas fa-lock'
    ACCESS_CONTROL_LIST = "fas fa-user-shield"
    HEALTH_STATE = "fas fa-heartbeat"


def get_icon(enum: IconEnum, color=None) -> SafeString:
    icon = f"<i class=\"{enum.value} {color}\"></i>" if color else f"<i class=\"{enum.value}\"></i>"
    return format_html(icon)


def get_all_icons() -> dict:
    icons = {}
    # if we do not iterate over __members__, duplicate enum values will be ignored.
    for name, enum in IconEnum.__members__.items():
        icons.update({name: get_icon(enum)})
    return icons
