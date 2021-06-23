from main.forms import ModelForm
from django import forms

from main.widgets import TreeSelectMultiple
from resourceNew.enums.service import OGCServiceEnum
from resourceNew.models import Layer, FeatureType, Service
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, ProxySetting, ExternalAuthentication
from leaflet.forms.widgets import LeafletWidget
from dal import autocomplete
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ExternalAuthenticationModelForm(ModelForm):
    class Meta:
        model = ExternalAuthentication
        fields = "__all__"
        widgets = {
            "password": forms.PasswordInput()
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance", None)
        if instance:
            username, password = instance.decrypt()
            instance.username = username
        super().__init__(*args, **kwargs)
        if kwargs.get("instance", None):
            self.fields["secured_service"].widget.attrs['disabled'] = True


class ServiceAccessGroupModelForm(ModelForm):
    class Meta:
        model = ServiceAccessGroup
        fields = ("name", "description")


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
            "operations": autocomplete.ModelSelect2Multiple(
                url='autocompletes:operations',
                attrs={
                    "data-containerCss": {
                        "height": "3em",
                        "width": "3em",
                    }
                },
            ),
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
                # 'display_raw': 'true',
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
            if secured_service.service_type_name == OGCServiceEnum.WMS.value:
                self.fields.pop("secured_feature_types")
                self.fields["secured_layers"].queryset = Layer.objects.filter(service=secured_service)
                self.fields["secured_layers"].widget = TreeSelectMultiple(tree=secured_service.root_layer.get_descendants(include_self=True).select_related("metadata"))
            elif secured_service.service_type_name == OGCServiceEnum.WFS.value:
                self.fields.pop("secured_layers")
                self.fields["secured_feature_types"].queryset = FeatureType.objects.filter(service=secured_service)
        else:
            # todo
            raise Exception

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
