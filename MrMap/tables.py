import random
import string

import django_filters
from django.http import HttpRequest
from django.template.loader import render_to_string
from django_tables2 import tables, RequestConfig
from MrMap.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, BTN_SM_CLASS
from MrMap.settings import PAGE_SIZE_OPTIONS, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT, PAGE_DEFAULT
from MrMap.utils import get_theme
from structure.models import Permission
from users.helper import user_helper


class MrMapTable(tables.Table):
    filter_set = None
    pagination = {}
    page_field = None
    caption = ""

    def __init__(self,
                 request=None,
                 filter_set_class=None,
                 queryset=None,
                 query_filter=None,
                 query_class=None,
                 current_view=None,
                 param_lead='mr-map-t',
                 *args,
                 **kwargs):
        # Generate a random id for html template
        self.table_id = ''.join(random.choice(string.ascii_lowercase) for i in range(10))
        self.request = request
        self.filter_set_class = filter_set_class
        self.queryset = queryset
        self.user = user_helper.get_user(request)
        self.current_view = current_view
        self.param_lead = param_lead
        # He we set the data kw dynamic by the query_class and query_filter,
        # so we don't need to set the data kw in every view again and again
        # ToDo: it's a little bit messy... refactor this if/else
        if queryset is not None:
            if filter_set_class:
                self._configure_filter_set()
                kwargs['data'] = self.filter_set.qs
            else:
                kwargs['data'] = queryset
        elif query_class:
            if query_filter:
                if filter_set_class:
                    self._configure_filter_set(queryset=query_class.objects.filter(query_filter))
                    kwargs['data'] = self.filter_set.qs
                else:
                    data = query_class.objects.filter(query_filter)
            else:
                if filter_set_class:
                    self._configure_filter_set(queryset=query_class.objects.all())
                    kwargs['data'] = self.filter_set.qs
                else:
                    data = query_class.objects.all()
            kwargs['data'] = data

        super(MrMapTable, self).__init__(template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, *args, **kwargs)
        self._configure_pagination()

    def _configure_filter_set(self, queryset=None):
        self.filter_set = self.filter_set_class(data=self.request.GET,
                                                queryset=queryset or self.queryset)

    def _configure_pagination(self):
        RequestConfig(self.request).configure(self)
        self.prepare_table_pagination_settings(self.request, self.param_lead)
        self.page_field = self.pagination.get('page_name')
        self.paginate(page=self.request.GET.get(self.pagination.get('page_name'), PAGE_DEFAULT),
                      per_page=self.request.GET.get(self.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    def get_link(self, href: str, value: str, tooltip: str, tooltip_placement: str, permission: Permission):
        if self.user.has_permission(permission):
            context = {
                "href": href,
                "value": value,
                "link_color": get_theme(self.user)["TABLE"]["LINK_COLOR"],
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
            }
            return render_to_string(template_name="sceletons/open-link.html",
                                    context=context)
        else:
            return ''

    def get_btn(self, href: str, btn_color: str, btn_value: str, permission: Permission, tooltip: str = '', tooltip_placement: str = 'left',):
        if self.user.has_permission(permission):
            context = {
                "btn_size": BTN_SM_CLASS,
                "btn_color": btn_color,
                "btn_value": btn_value,
                "btn_url": href,
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
            }
            return render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context)
        else:
            return ''

    def prepare_table_pagination_settings(self, request: HttpRequest, param_lead: str):
        return self.prepare_list_pagination_settings(request, list(self.rows), param_lead)

    def prepare_list_pagination_settings(self, request: HttpRequest, l: list, param_lead: str):
        page_size_options = list(filter(lambda item: item <= len(l), PAGE_SIZE_OPTIONS))

        if not page_size_options.__contains__(len(l)):
            page_size_options.append(len(l))

        page_size_options = list(filter(lambda item: item <= PAGE_SIZE_MAX, page_size_options))

        self.pagination = {'page_size_param': param_lead + '-size',
                           'page_size_options': page_size_options,
                           'page_name': param_lead + '-page'
                           }

        if PAGE_SIZE_DEFAULT <= page_size_options[-1]:
            page_size = PAGE_SIZE_DEFAULT
        else:
            page_size = page_size_options[-1]

        self.pagination.update({'page_size': request.GET.get(self.pagination.get('page_size_param'), page_size)})
