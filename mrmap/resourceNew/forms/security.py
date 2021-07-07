from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model

from main.forms import ModelForm
from django import forms

from main.widgets import TreeSelectMultiple
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.models import Layer, FeatureType, Service
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxySetting, ExternalAuthentication, \
    OGCOperation
from leaflet.forms.widgets import LeafletWidget
from dal import autocomplete
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from resourceNew.settings import SECURE_ABLE_WMS_OPERATIONS, SECURE_ABLE_WFS_OPERATIONS


class ExternalAuthenticationModelForm(ModelForm):
    secured_service = forms.ModelChoiceField(queryset=Service.objects.all(),
                                             widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = ExternalAuthentication
        fields = "__all__"
        widgets = {
            "password": forms.PasswordInput(render_value=True)
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance", None)
        if instance:
            username, password = instance.decrypt()
            instance.username = username
        super().__init__(*args, **kwargs)


class ServiceAccessGroupModelForm(ModelForm):
    user_set = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.all(),
        required=False,
        widget=autocomplete.ModelSelect2Multiple(
                url='autocompletes:users',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        help_text=_("Select the users which shall be member of this access group. If you select AnonymousUser, "
                    "all users are allowed."),
        label=_("users")
    )

    class Meta:
        model = ServiceAccessGroup
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['user_set'].initial = self.instance.user_set.all()

    def save(self, commit=True):
        group = super().save(commit=False)

        if commit:
            group.save()

        if group.pk:
            group.user_set.set(self.cleaned_data['user_set'])
            self.save_m2m()

        return group


class AllowedOperationPage1ModelForm(ModelForm):

    class Meta:
        model = AllowedOperation
        fields = ("secured_service", )
        widgets = {
            'secured_service': autocomplete.ModelSelect2(
                url='autocompletes:service',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        }


class AllowedOperationPage2ModelForm(ModelForm):

    class Meta:
        model = AllowedOperation
        fields = ("description",
                  "operations",
                  "allowed_groups",
                  "allowed_area",
                  "secured_service",
                  "secured_layers",
                  "secured_feature_types",)
        widgets = {
            "allowed_groups": autocomplete.ModelSelect2Multiple(
                url="autocompletes:service_access_group",
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
            "allowed_area": LeafletWidget(attrs={
                'map_height': '500px',
                'map_width': '100%',
                #'display_raw': 'true',
                'map_srid': 4326,
            }),
            "secured_service": forms.HiddenInput(),
            "secured_feature_types": autocomplete.ModelSelect2Multiple(
                url="autocompletes:feature_type",
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "secured_service" in self.initial:
            secured_service = Service.objects.select_related("service_type").get(pk=self.initial.get("secured_service"))
            ogc_operation_ac_url = None
            if secured_service.service_type_name == OGCServiceEnum.WMS.value:
                self.fields.pop("secured_feature_types")
                self.fields["secured_layers"].queryset = Layer.objects.filter(service=secured_service)
                self.fields["secured_layers"].widget = TreeSelectMultiple(tree=secured_service.root_layer.get_descendants(include_self=True).select_related("metadata"))
                self.fields["operations"].widget = autocomplete.ModelSelect2Multiple(
                    url="resourceNew.autocomplete:ogcoperation_wms_ac",
                    attrs={
                        "data-containerCss": {
                            "height": "3em",
                            "width": "3em",
                        }
                    },
                )
                self.fields["operations"].queryset = OGCOperation.objects.filter(operation__in=SECURE_ABLE_WMS_OPERATIONS)
            elif secured_service.service_type_name == OGCServiceEnum.WFS.value:
                self.fields.pop("secured_layers")
                self.fields["secured_feature_types"].queryset = FeatureType.objects.filter(service=secured_service)
                self.fields["operations"].widget = autocomplete.ModelSelect2Multiple(
                    url="resourceNew.autocomplete:ogcoperation_wfs_ac",
                    attrs={
                        "data-containerCss": {
                            "height": "3em",
                            "width": "3em",
                        }
                    },
                )
                self.fields["operations"].queryset = OGCOperation.objects.filter(operation__in=SECURE_ABLE_WFS_OPERATIONS)

        else:
            # todo
            raise NotImplemented

    def clean_secured_layers(self):
        configured_layers = self.cleaned_data.get("secured_layers")
        for layer in configured_layers:
            needed_layers = layer.get_descendants(include_self=True)
            if not all(layer in configured_layers for layer in needed_layers):
                raise ValidationError(message=_('Some sub layers are missing.'),
                                      code='invalid',)
        return configured_layers


class ProxySettingModelForm(ModelForm):
    class Meta:
        model = ProxySetting
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get("instance", None):
            self.fields["secured_service"].widget.attrs['disabled'] = True

            if self.instance.secured_service.allowed_operations.exists():
                self.fields["camouflage"].widget.attrs['readonly'] = True
