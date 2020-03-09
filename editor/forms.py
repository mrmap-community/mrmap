"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 09.07.19

"""
from dal import autocomplete
from django.forms import ModelForm, TextInput, CharField, CheckboxSelectMultiple, ModelChoiceField
from django.utils.translation import gettext_lazy as _

from service.models import Metadata, Keyword


class MetadataEditorForm(ModelForm):
    action_url = None

    #keywords = CharField(
    #    widget=TextInput(
    #        attrs={
    #            "autocomplete": "off"
    #        },
    #    ),
    #    help_text=_("Separate keywords from each other using comma.")
    #)

    def __init__(self, *args, **kwargs):
        # first call parent's constructor
        super(MetadataEditorForm, self).__init__(*args, **kwargs)

        # there's a `fields` property now
        self.fields['terms_of_use'].required = False

        # Transform list of ids to ',' separated keyword string
        #if kwargs.get("instance", None) is not None:
        #    self.initial["keywords"] = ",".join([k.keyword for k in self.instance.keywords.all()])

    #def clean_keywords(self):
    #    """ Resolve simple string keywords to database obejcts
#
    #    Returns:
    #         kw_records (list): A list of keyword records
    #    """
    #    super().clean()
    #    # Transform keywords into list of ids
    #    keywords = self.data.get("keywords", []).split(",")
#
    #    kw_records = []
    #    # All existing keyword
    #    for kw in keywords:
    #        kw_record = Keyword.objects.get_or_create(keyword=kw)[0]
    #        kw_records.append(kw_record)
#
    #    return kw_records

    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
            "access_constraints",
            "terms_of_use",
            "keywords",
            "categories",
        ]
        help_texts={
            "title": _("Edit the title."),
            "abstract": _("Edit the description. Keep it short and simple."),
            "access_constraints": _("Edit the access constraints."),
            "terms_of_use": _("Select another licence."),
            "keywords": _(""),  # Since keywords are handled differently, this can be empty
            "categories": _("Select categories for this resource."),
        }
        widgets = {
            "categories": CheckboxSelectMultiple(
                attrs={
                    "class": "",
                }
            ),
            'keywords': autocomplete.ModelSelect2Multiple(
                url='editor:keyword-autocomplete',
                attrs={
                    "containerCss": {
                        "height": "3em"
                    }
                },
            ),
        }



class FeatureTypeEditorForm(ModelForm):
    class Meta:
        model = Metadata
        fields = [
            "title",
            "abstract",
        ]