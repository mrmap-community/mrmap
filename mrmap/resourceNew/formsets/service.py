from extra_views import InlineFormSetFactory

from resourceNew.forms.security import ExternalAuthenticationModelForm, ProxySettingModelForm
from resourceNew.models.security import ExternalAuthentication, ProxySetting


class ExternalAuthenticationInline(InlineFormSetFactory):
    model = ExternalAuthentication
    form_class = ExternalAuthenticationModelForm

    def get_formset_kwargs(self):
        kwargs = super().get_formset_kwargs()
        kwargs['form_kwargs'] = {"request": self.request}
        return kwargs


class ProxySettingInline(InlineFormSetFactory):
    model = ProxySetting
    form_class = ProxySettingModelForm
    factory_kwargs = {"can_delete": False}

    def get_formset_kwargs(self):
        kwargs = super().get_formset_kwargs()
        kwargs['form_kwargs'] = {"request": self.request}
        return kwargs
