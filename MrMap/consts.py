"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 13.02.2020


This file holds all global constants
"""
from django.utils.html import format_html

DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE = "sceletons/django_tables2_bootstrap4_custom.html"

SERVICE_INDEX = "service:index"
SERVICE_DETAIL = "service:detail"
SERVICE_ADD = "service:add"

SERVICE_INDEX_LOG = "service:logs-view"

STRUCTURE_DETAIL_GROUP = "structure:detail-group"
STRUCTURE_INDEX_GROUP = "structure:groups-index"

STRUCTURE_DETAIL_ORGANIZATION = "structure:detail-organization"
STRUCTURE_INDEX_ORGANIZATION = "structure:organizations-index"

APP_XML = "application/xml"

URL_PATTERN = "<a class={} href='{}'>{}</a>"
URL_OPEN_IN_NEW_TAB_PATTERN = "<a class={} href='{}' target='_blank'>{}</a>"
URL_BTN_PATTERN = "<a class='{} {} {}' href='{}'>{}</a>"
URL_ICON_PATTERN = "<a class={} href='{}'>{}{}</a>"

BTN_CLASS = "btn"
BTN_SM_CLASS = "btn-sm"


def construct_url(classes: str, href: str, content: str, tooltip: str = None, new_tab: bool = False,):
    if new_tab:
        url = format_html(f"<a class={classes} href='{href}' target='_blank'>{content}</a>")
    else:
        url = format_html(f"<a class={classes} href='{href}'>{content}</a>")
    if tooltip:
        url = _construct_tooltip(tooltip=tooltip, content=url)
    return url


def _construct_tooltip(tooltip: str, content: str):
    return format_html(
        f"<span class='d-inline-block' tabindex='0' data-html='true' data-toggle='tooltip' title='{tooltip}'>{content}</span>")
