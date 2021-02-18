import uuid

from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse_lazy, resolve, reverse
from django.views import View
from django.views.generic import UpdateView, DetailView, TemplateView
from django.views.generic.base import ContextMixin
from django.views.generic.edit import FormMixin, FormView
from django_bootstrap_swt.components import Alert
from django_bootstrap_swt.enums import AlertEnum, ButtonColorEnum
from django_bootstrap_swt.utils import RenderHelper
from django_tables2 import SingleTableMixin
from django.utils.translation import gettext_lazy as _
from MrMap.forms import ConfirmForm
from MrMap.responses import DefaultContext
from MrMap.wizards import get_class


class ModalFormMixin(FormView):
    template_name = "generic_views/generic_modal.html"
    fade = True
    show = True
    size = 'modal-lg'
    id = "id_" + str(uuid.uuid4())
    action_url = ""
    current_view_arg = None
    current_view = None
    # Todo: move this to settings.py
    current_view_queryparam = 'current-view'
    current_view_arg_queryparam = 'current-view-arg'
    current_view_url = ""

    def prepare_query_params(self):
        query_params = f"?{self.current_view_queryparam}={self.current_view}"
        if self.current_view_arg:
            query_params += f"&{self.current_view_arg_queryparam}={self.current_view_arg}"
        return query_params

    def dispatch(self, request, *args, **kwargs):
        self.current_view = request.GET.get(self.current_view_queryparam, None)
        if not self.current_view:
            raise ImproperlyConfigured(f"query param '{self.current_view_queryparam}' "
                                       f"was not found in the url query parameters")
        self.current_view_arg = request.GET.get(self.current_view_arg_queryparam, None)

        if self.current_view_arg:
            self.current_view_url = reverse(f"{self.current_view}", args=[self.current_view_arg, ])
        else:
            self.current_view_url = reverse(f"{self.current_view}", )

        self.action_url += self.prepare_query_params()
        self.success_url = self.current_view_url
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.__dict__)
        return context

    def render_to_response(self, context, **response_kwargs):
        rendered_modal = render_to_string(template_name=self.template_name,
                                          context=context,
                                          request=self.request)
        resolver_match = resolve(self.current_view_url)
        # todo: catch simple non class based views
        func = resolver_match.func
        module = func.__module__
        view_name = func.__name__
        clss = get_class('{0}.{1}'.format(module, view_name))

        factory = RequestFactory()
        request = factory.get(self.current_view_url)
        request.user = self.request.user

        return clss.as_view(extra_context={'rendered_modal': rendered_modal})(request=request)


class GenericUpdateView(UpdateView):
    template_name = 'generic_views/generic_update.html'
    action = ""
    action_url = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"action": self.action,
                        "action_url": self.action_url})
        return context


class AsyncUpdateView(GenericUpdateView):
    alert_msg = ""
    async_task_func = None
    async_task_params = {}

    def form_valid(self, form):
        self.object.save()

        task = self.async_task_func.delay(object_id=self.object.id,
                                          additional_params=self.async_task_params)

        content = {
            "data": {
                "id": task.task_id,
            },
            "alert": Alert(msg=self.alert_msg, alert_type=AlertEnum.SUCCESS).render()
        }

        # cause this is a async task which can take longer we response with 'accept' status
        return JsonResponse(status=202, data=content)


class ModelFormView(FormMixin, DetailView):
    template_name = 'generic_views/generic_confirm_form.html'
    success_url = reverse_lazy('home')
    action = ""
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
        context.update({"action": self.action,
                        "action_url": self.action_url,
                        "action_btn_color": self.action_btn_color, })
        context = DefaultContext(request=self.request, context=context).get_context()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'instance': self.object})
        return kwargs

    def form_valid(self, form):
        form.save()
        return super().form_valid(form=form)


class ConfirmView(FormMixin, DetailView):
    template_name = 'generic_views/generic_confirm_form.html'
    success_url = reverse_lazy('home')
    form_class = ConfirmForm
    action = ""
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
        context.update({"action": self.action,
                        "action_url": self.action_url,
                        "action_btn_color": self.action_btn_color,})
        return context

    def get_success_url(self):
        return self.object.detail_view_uri


class AsyncConfirmView(ConfirmView):
    alert_msg = ""
    async_task_func = None
    async_task_params = {}

    def form_valid(self, form):
        self.object.save()

        task = self.async_task_func.delay(object_id=self.object.id,
                                          additional_params=self.async_task_params)

        content = {
            "data": {
                "id": task.task_id,
            },
            "alert": Alert(msg=self.alert_msg, alert_type=AlertEnum.SUCCESS).render()
        }

        # cause this is a async task which can take longer we response with 'accept' status
        return JsonResponse(status=202, data=content)


class InitFormMixin(FormMixin):
    def get_initial(self):
        initial = super().get_initial()
        initial.update(self.request.GET.copy())
        return initial


class GenericViewContextMixin(ContextMixin):
    title = None

    def get_title(self):
        return self.title

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"title": self.get_title})
        return context


class CustomSingleTableMixin(SingleTableMixin):
    title = None
    template_extend_base = True

    def get_title(self):
        if not self.title:
            instance = self.model()
            if hasattr(instance, 'icon'):
                return instance.icon + ' ' + instance._meta.verbose_name_plural.__str__()
            else:
                return instance._meta.verbose_name_plural
        return self.title

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(CustomSingleTableMixin, self).get_table(**kwargs)
        table.title = self.get_title()
        model = self.model()
        if hasattr(model, 'get_add_action') and callable(model.get_add_action):
            render_helper = RenderHelper(user_permissions=list(filter(None, self.request.user.get_permissions())))
            table.actions = [render_helper.render_item(item=self.model.get_add_action())]
        return table

    def get_template_extend_base(self):
        return self.template_extend_base

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": self.request.GET.get('per_page', 5), }

        if not self.template_name:
            self.template_extend_base = bool(self.request.GET.get('with-base', self.get_template_extend_base()))
            if self.template_extend_base:
                self.template_name = 'generic_views/generic_list_with_base.html'
            else:
                self.template_name = 'generic_views/generic_list_without_base.html'
        return super(CustomSingleTableMixin, self).dispatch(request, *args, **kwargs)


class DependingListView(View):
    depending_model = None
    object = None

    def setup(self, request, *args, **kwargs):
        if not self.depending_model:
            raise ImproperlyConfigured(_('You need to define a depending model class by setting the depending_model '
                                         'attribute.'))
        super().setup(request, *args, **kwargs)
        self.object = get_object_or_404(klass=self.depending_model, pk=kwargs.get('pk'))
