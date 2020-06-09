from django.forms import ModelForm
from django import forms
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from users.helper import user_helper


class MrMapModelForm(ModelForm):
    def __init__(self, form_title: str = "", has_autocomplete_fields: bool = False, *args, **kwargs):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        action_url = '' if 'action_url' not in kwargs else kwargs.pop('action_url')
        request = kwargs.pop('request')
        # first call parent's constructor
        super(MrMapModelForm, self).__init__(*args, **kwargs)
        self.action_url = action_url
        self.request = request
        self.requesting_user = user_helper.get_user(request)

        self.form_title = form_title
        self.has_autocomplete_fields = has_autocomplete_fields


class MrMapForm(forms.Form):
    def __init__(self, form_title: str = "", has_autocomplete_fields: bool = False, *args, **kwargs, ):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        action_url = '' if 'action_url' not in kwargs else kwargs.pop('action_url')
        request = kwargs.pop('request')
        # first call parent's constructor
        super(MrMapForm, self).__init__(*args, **kwargs)
        self.action_url = action_url
        self.request = request
        self.requesting_user = user_helper.get_user(request)

        self.form_title = form_title
        self.has_autocomplete_fields = has_autocomplete_fields


class MrMapWizardForm(forms.Form):
    def __init__(self, request: HttpRequest, instance_id: int = None, has_autocomplete_fields: bool = False, *args, **kwargs):
        super(MrMapWizardForm, self).__init__(*args, **kwargs)
        self.request = request
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


class MrMapFormList:
    def __init__(self, form_list: list, action_url: str):
        self.form_list = form_list
        self.action_url = action_url
