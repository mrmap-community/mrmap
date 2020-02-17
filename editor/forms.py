"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from django.forms import ModelForm, CheckboxInput, CheckboxSelectMultiple
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django import forms
from django.forms.utils import flatatt

from service.models import Metadata, Group


class MetadataEditorForm(ModelForm):
    action_url = None

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "use_proxy_uri",
            "categories",
            "keywords",
        ]
        labels = {
            "use_proxy_uri": _("Use proxy"),
        }
        widgets = {
            "use_proxy_uri": CheckboxInput(),
            "categories": CheckboxSelectMultiple(),
            "keywords": CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False
        self.fields['categories'].required = False
        self.fields['keywords'].required = False


class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]


class AccessIsRootForm(forms.Form):
    is_use_proxy = forms.BooleanField(required=False, label="Use proxy", widget=forms.CheckboxInput(), initial=False)
    is_log_proxy = forms.BooleanField(required=False, label="Log proxy", widget=forms.CheckboxInput(), initial=False)


class AccessRestrictAccessForm(forms.Form):
    is_restricted = forms.BooleanField(required=False, label="Restrict access", widget=forms.CheckboxInput(), initial=False)


class AccessGroupForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(queryset=None, to_field_name='id', widget=CheckboxSelectMultiple())

    def __init__(self, *args, **kwargs):
        # pop custom kwargs before invoke super constructor and hold them
        self.groups_queryset = kwargs.pop('groups_queryset')

        # run super constructor to construct the form
        super(AccessGroupForm, self).__init__(*args, **kwargs)

        # initial the fields with the poped kwargs
        self.fields['groups'].queryset = self.groups_queryset


class AccessGroupGeoJsonForm(forms.Form):
    group_id = None
    group_name = None
    geo_json_geometry = forms.CharField(required=False, widget=forms.Textarea(), disabled=True,)

    def __init__(self, *args, **kwargs):
        # pop custom kwargs before invoke super constructor and hold them
        self.geo_json_geometry_id = kwargs.pop('geo_json_geometry_id')

        # run super constructor to construct the form
        super(AccessGroupGeoJsonForm, self).__init__(*args, **kwargs)

        # initial the fields with the poped kwargs
        self.fields['geo_json_geometry'].widget.attrs = {'placeholder': 'No spatial restriction for this group.',
                                                         'id': 'id_geo_json_group_' + str(self.geo_json_geometry_id)}
