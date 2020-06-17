from django.http import HttpResponseRedirect
from django.urls import reverse
from MrMap.wizards import MrMapWizard
from editor.forms import DatasetIdentificationForm, DatasetClassificationForm, DatasetTemporalExtentForm, \
    DatasetLicenseConstraintsForm, DatasetSpatialExtentForm
from django.utils.translation import gettext_lazy as _

DATASET_WIZARD_FORMS = [(_("identification"), DatasetIdentificationForm),
                        (_("classification"), DatasetClassificationForm),
                        (_("spatial extent"), DatasetSpatialExtentForm),
                        (_("licenses/constraints"), DatasetLicenseConstraintsForm),
                        (_("maintenance information"), DatasetTemporalExtentForm),]


class DatasetWizard(MrMapWizard):

    def done(self, form_list, **kwargs):
        for form in form_list:
            # ToDo: save input of all forms
            pass

        return HttpResponseRedirect(reverse(self.kwargs['current_view'], ), status=303)
