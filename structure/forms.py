from django import forms
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from structure.models import Group


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)


class GroupForm(ModelForm):
    description = forms.CharField(
        widget=forms.Textarea()
    )
    class Meta:
        model = Group
        fields = '__all__'
        exclude = ["created_by"]
