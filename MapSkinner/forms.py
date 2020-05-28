from django.forms import ModelForm
from django import forms
from django.utils.translation import gettext_lazy as _


class MrMapModelForm(ModelForm):
    def __init__(self, *args, **kwargs):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        action_url = '' if 'action_url' not in kwargs else kwargs.pop('action_url')
        # first call parent's constructor
        super(MrMapModelForm, self).__init__(*args, **kwargs)
        self.action_url = action_url


class MrMapForm(forms.Form):
    def __init__(self, *args, **kwargs):
        """
            @keyword action_url: the action_url is a mandatory keyword, which is used in our modal-form skeleton to
            dynamically configure the right action_url for the form
        """
        self.action_url = '' if 'action_url' not in kwargs else kwargs.pop('action_url')
        # first call parent's constructor
        super(MrMapForm, self).__init__(*args, **kwargs)


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
