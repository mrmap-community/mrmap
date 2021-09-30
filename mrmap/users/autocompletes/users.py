from dal import autocomplete
from guardian.mixins import LoginRequiredMixin
from users.models import MrMapUser


class MrMapUserAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    model = MrMapUser
    search_fields = ['username']
