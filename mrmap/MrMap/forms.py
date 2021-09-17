from django import forms
from django.utils.translation import gettext_lazy as _
from main.forms import Form

CURRENT_VIEW_QUERY_PARAM = 'current-view'
CURRENT_VIEW_ARG_QUERY_PARAM = 'current-view-arg'


class ConfirmForm(Form):
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
