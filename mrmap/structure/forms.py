from captcha.fields import CaptchaField
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from structure.models import Organization


class OrganizationChangeForm(forms.ModelForm):
    """
    ModelForm that adds handling for reverse relation `publishers` for the given `Organization`.
    """
    publishers = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.none(),
        required=False,
        help_text=_('All organizations which can publish for this organization')
    )

    class Meta:
        model = Organization
        fields = '__all__'
        exclude = ('can_publish_for', )

    def __init__(self, *args, **kwargs):
        super(OrganizationChangeForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            publishers = Organization.objects.filter(can_publish_for=self.instance).values_list('pk', flat=True)
            self.initial['publishers'] = publishers
            self.fields['publishers'].queryset = Organization.objects.filter(~Q(pk=self.instance.pk))

    def save(self, *args, **kwargs):
        saved_object = super(OrganizationChangeForm, self).save(*args, **kwargs)
        init_publishers = Organization.objects.filter(id__in=self.initial['publishers'])

        removed_publishers = init_publishers.exclude(id__in=self.cleaned_data['publishers'])
        added_publishers = self.cleaned_data['publishers'].exclude(id__in=self.initial['publishers'])

        for publisher in removed_publishers:
            publisher.can_publish_for.remove(self.instance)

        for publisher in added_publishers:
            publisher.can_publish_for.add(self.instance)

        return saved_object


class RegistrationForm(UserCreationForm):

    email = forms.EmailField(required=True)

    dsgvo = forms.BooleanField(
        initial=False,
        label=_("I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR)."),
        required=True
    )
    captcha = CaptchaField(label=_("I'm not a robot"), required=True)

    class Meta:
        model = get_user_model()
        fields = ('username',
                  'password1',
                  'password2',
                  'first_name',
                  'last_name',
                  'email',
                  'confirmed_newsletter',
                  'confirmed_survey',
                  'dsgvo',
                  'captcha')

    def clean(self):
        cleaned_data = super(RegistrationForm, self).clean()

        # Username taken check
        u_name = cleaned_data.get("username", None)
        u_exists = get_user_model().objects.filter(username=u_name).exists()
        if u_exists:
            self.add_error("username", forms.ValidationError(_("Username is already taken. Try another.")))
        return cleaned_data

    def save(self, commit=True):
        self.instance.person_name = self.instance.first_name + " " + self.instance.last_name
        self.instance.is_active = False
        return super().save(commit=commit)
