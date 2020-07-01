import random
import string
from django.http import HttpRequest
from django.template.loader import render_to_string
from django_tables2 import tables, RequestConfig
from MrMap.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, BTN_SM_CLASS
from MrMap.settings import PAGE_SIZE_OPTIONS, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT, PAGE_DEFAULT
from MrMap.utils import get_theme
from structure.models import Permission
from users.helper import user_helper


class MrMapTable(tables.Table):
    filter = None
    pagination = {}
    page_field = None
    caption = ""

    def __init__(self, request=None, query_filter=None, query_class=None, *args, **kwargs):
        # Generate a random id for html template
        self.table_id = ''.join(random.choice(string.ascii_lowercase) for i in range(10))
        self.request = request
        self.user = user_helper.get_user(request)

        if query_class:
            if query_filter:
                data = query_class.objects.filter(query_filter)
            else:
                data = query_class.objects.all()
            kwargs['data'] = data

        super(MrMapTable, self).__init__(template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, *args, **kwargs)

    def configure_pagination(self, request: HttpRequest, param_lead: str):
        RequestConfig(request).configure(self)
        self.prepare_table_pagination_settings(request, param_lead)
        self.page_field = self.pagination.get('page_name')
        self.paginate(page=request.GET.get(self.pagination.get('page_name'), PAGE_DEFAULT),
                      per_page=request.GET.get(self.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    def get_edit_btn(self, href: str, tooltip: str, tooltip_placement: str, permission: Permission):
        if self.user.has_permission(permission):
            context_edit_btn = {
                "btn_size": BTN_SM_CLASS,
                "btn_color": get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                "btn_value": get_theme(self.user)["ICONS"]['EDIT'],
                "btn_url": href,
                "tooltip": tooltip,
                "tooltip_placement": tooltip_placement,
            }
            return render_to_string(template_name="sceletons/open-link-button.html",
                                    context=context_edit_btn)
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
