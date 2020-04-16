from django.http import HttpRequest
from django_tables2 import tables, RequestConfig
from django_tables2.templatetags import django_tables2

from MapSkinner.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from MapSkinner.settings import PAGE_SIZE_OPTIONS, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT, PAGE_DEFAULT


def prepare_table_pagination_settings(request: HttpRequest, table: django_tables2, param_lead: str):
    return prepare_list_pagination_settings(request, list(table.rows), param_lead)


def prepare_list_pagination_settings(request: HttpRequest, l: list, param_lead: str):
    page_size_options = list(filter(lambda item: item <= len(l), PAGE_SIZE_OPTIONS))

    if not page_size_options.__contains__(len(l)):
        page_size_options.append(len(l))

    page_size_options = list(filter(lambda item: item <= PAGE_SIZE_MAX, page_size_options))

    pagination = {'page_size_param': param_lead + '-size',
                  'page_size_options': page_size_options,
                  'page_name': param_lead + '-page'
                  }

    if PAGE_SIZE_DEFAULT <= page_size_options[-1]:
        page_size = PAGE_SIZE_DEFAULT
    else:
        page_size = page_size_options[-1]

    pagination.update({'page_size': request.GET.get(pagination.get('page_size_param'), page_size)})

    return pagination


class MapSkinnerTable(tables.Table):
    filter = None
    pagination = None
    page_field = None

    def configure_pagination(self, request: HttpRequest, param_lead: str):
        RequestConfig(request).configure(self)
        self.pagination = prepare_table_pagination_settings(request, self, param_lead)
        self.page_field = self.pagination.get('page_name')
        self.paginate(page=request.GET.get(self.pagination.get('page_name'), PAGE_DEFAULT),
                      per_page=request.GET.get(self.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    def __init__(self, *args, **kwargs):
        super().__init__(template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, *args, **kwargs)
