import uuid
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DetailView
from django.views.generic.base import ContextMixin
from django.views.generic.edit import FormMixin, FormView
from extras.enums.bootstrap import AlertEnum, ButtonColorEnum
from django_tables2 import SingleTableMixin, LazyPaginator
from django.utils.translation import gettext_lazy as _
from MrMap.forms import ConfirmForm


class ConfirmView(FormMixin, DetailView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_url = reverse_lazy('users:dashboard')
    form_class = ConfirmForm
    action_url = ""
    action_btn_color = ButtonColorEnum.PRIMARY

    # decorator or some other function could pass *args or **kwargs it to this function
    # so keep *args and **kwargs here to avoid from
    # TypeError: post() got an unexpected keyword argument 'pk' for example
    def post(self, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"action_url": self.action_url,
                        "action_btn_color": self.action_btn_color,})
        return context

    def get_success_url(self):
        return self.object.get_absolute_url()


class InitFormMixin(FormMixin):

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET.copy())
        return initial


class GenericViewContextMixin(ContextMixin):
    title = None

    def get_title(self):
        if self.title:
            return self.title
        else:
            if hasattr(self, 'action'):
                return f"{self.action.capitalize()} {self.model._meta.verbose_name}"
            else:
                return self.model._meta.verbose_name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"title": self.get_title})
        return context


class SuccessMessageDeleteMixin:
    """
    Add a success message on successful delete object.
    """
    success_message = ''
    msg_dict = {}

    def delete(self, request, *args, **kwargs):
        success_message = self.get_success_message()

        response = super().delete(request, *args, **kwargs)

        if success_message:
            messages.success(self.request, success_message)
        return response

    def get_success_message(self):
        return self.success_message % self.get_msg_dict()

    def get_msg_dict(self):
        return self.msg_dict


class CustomSingleTableMixin(SingleTableMixin):
    title = None
    template_extend_base = True
    add_url = None
    # Implement lazy pagination, preventing any count() queries to increase performance.
    # todo: disabled since refactoring service app to registry app... we need to to test the performance of all
    #  table views. If we got performance problems we could activate the LazyPaginator again. But for the user
    #  experience it would be better to dispense LazyPaginator cause with the default pagination we can show total
    #  table count.
    # paginator_class = LazyPaginator

    def get_title(self):
        if not self.title:
            instance = self.model()
            if hasattr(instance, 'icon'):
                return instance.icon + ' ' + instance._meta.verbose_name_plural.__str__().title()
            else:
                return instance._meta.verbose_name_plural.__str__().title()
        return self.title

    def get_add_url(self):
        if not self.add_url and hasattr(self.model(), "get_add_url"):
            return self.model().get_add_url()
        return self.add_url

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super().get_table(**kwargs)
        table.title = self.get_title()
        table.add_url = self.get_add_url()
        return table

    def get_template_extend_base(self):
        return self.template_extend_base

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        try:
            per_page = int(self.request.GET.get('per_page', settings.PER_PAGE_DEFAULT))
        except ValueError:
            per_page = settings.PER_PAGE_DEFAULT
        if per_page > settings.PER_PAGE_MAX:
            per_page = settings.PER_PAGE_MAX
        self.table_pagination = {"per_page": per_page}

        if not self.template_name:
            self.template_extend_base = bool(self.request.GET.get('with-base', self.get_template_extend_base()))
            if self.template_extend_base:
                self.template_name = 'generic_views/generic_list_with_base.html'
            else:
                self.template_name = 'generic_views/generic_list_without_base.html'
        return super().dispatch(request, *args, **kwargs)


class DependingListMixin:
    depending_model = None
    depending_field_name = None
    object = None

    def setup(self, request, *args, **kwargs):
        if not self.depending_model:
            raise ImproperlyConfigured(_('You need to define a depending model class by setting the depending_model '
                                         'attribute.'))
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=self.depending_model, pk=kwargs.get('pk'))

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(Q(**{self.depending_field_name: self.object}))
