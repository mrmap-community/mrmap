import uuid

from django.http import HttpRequest
from django.template.loader import render_to_string
from django_tables2 import tables, RequestConfig
from django.utils.translation import gettext_lazy as _

from MrMap.columns import MrMapColumn
from MrMap.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from MrMap.settings import PAGE_SIZE_OPTIONS, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT, PAGE_DEFAULT
from structure.permissionEnums import PermissionEnum
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
        self.table_id = str(uuid.uuid4())
        self.request = request
        self.filter_set_class = filter_set_class
        self.queryset = queryset
        self.user = user_helper.get_user(request)
        self.current_view = current_view
        self.param_lead = param_lead

        self.permission_lookup = {}

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
        self.filter_set = self.filter_set_class(
            data=self.request.GET,
            queryset=queryset or self.queryset,
            request=self.request,
        )

    def _configure_pagination(self):
        RequestConfig(self.request).configure(self)
        self.prepare_table_pagination_settings(self.request, self.param_lead)
        self.page_field = self.pagination.get('page_name')
        self.paginate(page=self.request.GET.get(self.pagination.get('page_name'), PAGE_DEFAULT),
                      per_page=self.request.GET.get(self.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    def check_render_permission(self, permission: PermissionEnum):
        has_perm = self.permission_lookup.get(permission, None)
        if has_perm is None:
            has_perm = self.user.has_perm(perm=permission)
            self.permission_lookup[permission] = has_perm
        return has_perm


    def prepare_table_pagination_settings(self, request: HttpRequest, param_lead: str):
        return self.prepare_list_pagination_settings(request, param_lead)

    def prepare_list_pagination_settings(self, request: HttpRequest, param_lead: str):
        len_rows = len(self.rows)
        page_size_options = list(filter(lambda item: item <= len_rows, PAGE_SIZE_OPTIONS))

        if len_rows not in page_size_options:
            page_size_options.append(len_rows)

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


class ActionTableMixin(tables.Table):
    actions = MrMapColumn(
        verbose_name=_('Actions'),
        tooltip=_('Actions you can perform'),
        empty_values=[],
        orderable=False,
        attrs={"td": {"class": "text-right",
                      "style": "white-space:nowrap; width: auto !important;"},
               "th": {"style": "width: 1px;"}
               }
    )


