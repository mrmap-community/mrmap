import uuid
from django.forms import ModelForm
from django import forms
from django.http import HttpRequest, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse, resolve
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from MrMap.responses import DefaultContext

CURRENT_VIEW_QUERY_PARAM = 'current-view'
CURRENT_VIEW_ARG_QUERY_PARAM = 'current-view-arg'


def get_current_view_args(request: HttpRequest):
    current_view = request.GET.get(CURRENT_VIEW_QUERY_PARAM, request.resolver_match.view_name)
    if request.resolver_match.kwargs:
        # if kwargs are not empty, this is a detail view
        if 'pk' in request.resolver_match.kwargs:
            current_view_arg = request.resolver_match.kwargs['pk']
        else:
            current_view_arg = request.resolver_match.kwargs['slug']
        current_view_arg = request.GET.get('current-view-arg', current_view_arg)
        url_qs_dict = {CURRENT_VIEW_QUERY_PARAM: current_view,
                       CURRENT_VIEW_ARG_QUERY_PARAM: current_view_arg}
    else:
        url_qs_dict = {CURRENT_VIEW_QUERY_PARAM: current_view}

    return url_qs_dict


class MrMapModalForm:
    current_view_arg = None

    def __init__(self,
                 request: HttpRequest,
                 form_title: str = _("Form"),
                 has_autocomplete_fields: bool = False,
                 # ToDo: in future reverse_lookup and current_view become a non default kw
                 reverse_lookup: str = None,
                 reverse_args: list = None,
                 # Todo: action_url as constructor kw is deprecated
                 action_url: str = None,
                 template_name: str = None,
                 default_context: dict = None,
                 show_modal: bool = False,
                 fade_modal: bool = True,
                 *args,
                 **kwargs, ):

        self.form_id = uuid.uuid4()
        self.request = request
        self.requesting_user = request.user
        self.form_title = format_html(form_title)
        self.has_autocomplete_fields = has_autocomplete_fields
        self.reverse_lookup = reverse_lookup
        self.reverse_args = reverse_args
        self.template_name = template_name or 'skeletons/modal_form.html'
        self.default_context = default_context or DefaultContext(request, {}, self.requesting_user).context
        self.show_modal = show_modal
        self.fade_modal = fade_modal
        self.current_view = self.request.GET.get(CURRENT_VIEW_QUERY_PARAM, "home")
        current_view_arg = self.request.GET.get('current-view-arg', None)
        self.current_view_arg = current_view_arg
        if current_view_arg is not None and current_view_arg.isnumeric():
            self.current_view_arg = int(current_view_arg)

        action_url_queryparams = f"?{CURRENT_VIEW_QUERY_PARAM}={self.current_view}&current-view-arg={self.current_view_arg}" \
                                 if self.current_view_arg else f"?{CURRENT_VIEW_QUERY_PARAM}={self.current_view}"
        self.action_url = reverse(self.reverse_lookup, args=self.reverse_args) + action_url_queryparams \
                          if self.reverse_lookup else action_url

    def _render_form_as_string(self,):
        self.default_context.update({'form': self})
        return render_to_string(request=self.request,
                                template_name=self.template_name,
                                context=self.default_context)

    def render_view(self, status_code: int = 200):
        view_function = resolve(reverse(viewname=self.current_view, )) if self.current_view_arg is None \
            else resolve(reverse(viewname=self.current_view, args=[self.current_view_arg, ]))
        if self.current_view_arg:
            if 'pk' in view_function.kwargs:
                return view_function.func(request=self.request,
                                          status_code=status_code,
                                          update_params={'current_view': self.current_view,
                                                         'rendered_modal': self._render_form_as_string()},
                                          pk=self.current_view_arg,)
            else:
                return view_function.func(request=self.request,
                                          status_code=status_code,
                                          update_params={'current_view': self.current_view,
                                                         'rendered_modal': self._render_form_as_string()},
                                          slug=self.current_view_arg, )
        else:
            return view_function.func(request=self.request,
                                      status_code=status_code,
                                      update_params={'current_view': self.current_view,
                                                     'rendered_modal': self._render_form_as_string()}, )

    def process_request(self, valid_func):
        if self.request.method == 'GET':
            return self.render_view()

        if self.request.method == 'POST':
            if self.is_valid():
                valid_func()
            else:
                self.fade_modal = False
                return self.render_view(status_code=422)

        if 'current-view-arg' in self.request.GET:
            return HttpResponseRedirect(reverse(self.request.GET.get('current-view'), args=(self.request.GET.get('current-view-arg'),)), status=303)
        else:
            return HttpResponseRedirect(reverse(self.request.GET.get(CURRENT_VIEW_QUERY_PARAM, 'home'), ), status=303)


class MrMapForm(forms.Form, MrMapModalForm):
    def __init__(self,
                 request: HttpRequest,
                 form_title: str = _("Form"),
                 has_autocomplete_fields: bool = False,
                 # ToDo: in future reverse_lookup and current_view become a non default kw
                 reverse_lookup: str = None,
                 reverse_args: list = None,
                 # Todo: action_url as constructor kw is deprecated
                 action_url: str = None,
                 template_name: str = None,
                 default_context: dict = None,
                 # ToDo: show_modal default should be true
                 show_modal: bool = False,
                 fade_modal: bool = True,
                 *args,
                 **kwargs):
        MrMapModalForm.__init__(self,
                                request,
                                form_title,
                                has_autocomplete_fields,
                                reverse_lookup,
                                reverse_args,
                                action_url,
                                template_name,
                                default_context,
                                show_modal,
                                fade_modal,
                                *args,
                                **kwargs)
        forms.Form.__init__(self,  *args, **kwargs)


class MrMapModelForm(ModelForm, MrMapModalForm):
    def __init__(self,
                 request: HttpRequest,
                 form_title: str = _("Form"),
                 has_autocomplete_fields: bool = False,
                 # ToDo: in future reverse_lookup and current_view become a non default kw
                 reverse_lookup: str = None,
                 reverse_args: list = None,
                 # Todo: action_url as constructor kw is deprecated
                 action_url: str = None,
                 template_name: str = None,
                 default_context: dict = None,
                 # ToDo: show_modal default should be true
                 show_modal: bool = False,
                 fade_modal: bool = True,
                 *args,
                 **kwargs):
        MrMapModalForm.__init__(self,
                                request,
                                form_title,
                                has_autocomplete_fields,
                                reverse_lookup,
                                reverse_args,
                                action_url,
                                template_name,
                                default_context,
                                show_modal,
                                fade_modal,
                                *args,
                                **kwargs)
        ModelForm.__init__(self, *args, **kwargs)


class MrMapWizardForm(forms.Form):

    def __init__(self,
                 request: HttpRequest,
                 instance_id: int = None,
                 has_autocomplete_fields: bool = False,
                 *args,
                 **kwargs):

        super(MrMapWizardForm, self).__init__(*args, **kwargs)
        self.request = request
        self.requesting_user = request.user
        self.instance_id = instance_id
        self.has_autocomplete_fields = has_autocomplete_fields

    def has_required_fields(self):
        for key in self.fields:
            field_object = self.fields[key]
            if field_object.required:
                return True
        return False


class MrMapWizardModelForm(ModelForm):
    def __init__(self, request: HttpRequest, instance_id: int = None, has_autocomplete_fields: bool = False, *args, **kwargs):
        super(MrMapWizardModelForm, self).__init__(*args, **kwargs)
        self.request = request
        self.instance_id = instance_id
        self.has_autocomplete_fields = has_autocomplete_fields

    def has_required_fields(self):
        for key in self.fields:
            field_object = self.fields[key]
            if field_object.required:
                return True
        return False


class MrMapConfirmForm(MrMapForm):
    is_confirmed = forms.BooleanField()

    def __init__(self, *args, **kwargs):
        is_confirmed_label = '' if 'is_confirmed_label' not in kwargs else kwargs.pop('is_confirmed_label')
        super(MrMapConfirmForm, self).__init__(*args, **kwargs)
        self.fields["is_confirmed"].label = is_confirmed_label

    def clean(self):
        cleaned_data = super(MrMapConfirmForm, self).clean()
        is_confirmed = cleaned_data.get("is_confirmed")
        if is_confirmed is not True:
            self.add_error("is_confirmed", _("Check this field"))
        return cleaned_data


class ConfirmForm(forms.Form):
    is_confirmed = forms.BooleanField()

    def __init__(self, *args, **kwargs):
        is_confirmed_label = '' if 'is_confirmed_label' not in kwargs else kwargs.pop('is_confirmed_label')
        super(ConfirmForm, self).__init__(*args, **kwargs)
        self.fields["is_confirmed"].label = is_confirmed_label

    def clean(self):
        cleaned_data = super(ConfirmForm, self).clean()
        is_confirmed = cleaned_data.get("is_confirmed")
        if is_confirmed is not True:
            self.add_error("is_confirmed", _("Check this field"))
        return cleaned_data
