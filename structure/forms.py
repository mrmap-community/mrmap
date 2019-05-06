from django import forms
from django.utils.translation import gettext_lazy as _

class LoginForm(forms.Form):
    username = forms.CharField(max_length=255, label=_("Username"), label_suffix=" ")
    password = forms.CharField(max_length=255, label=_("Password"), label_suffix=" ", widget=forms.PasswordInput)
