"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 13.02.2020


This file holds all global constants
"""
from django.utils.html import format_html

DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE = "sceletons/django_tables2_bootstrap4_custom.html"

SERVICE_INDEX = "resource:index"
SERVICE_DETAIL = "resource:detail"
SERVICE_ADD = "resource:add"

SERVICE_INDEX_LOG = "resource:logs-view"

STRUCTURE_DETAIL_GROUP = "structure:group_details"
STRUCTURE_INDEX_GROUP = "structure:groups-index"

STRUCTURE_DETAIL_ORGANIZATION = "structure:organization_details"
STRUCTURE_INDEX_ORGANIZATION = "structure:organization_overview"

APP_XML = "application/xml"

URL_PATTERN = "<a class={} href='{}'>{}</a>"
URL_OPEN_IN_NEW_TAB_PATTERN = "<a class={} href='{}' target='_blank'>{}</a>"
URL_BTN_PATTERN = "<a class='{} {} {}' href='{}'>{}</a>"
URL_ICON_PATTERN = "<a class={} href='{}'>{}{}</a>"

BTN_CLASS = "btn"
BTN_SM_CLASS = "btn-sm"
