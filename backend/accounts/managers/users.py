from django.contrib.auth.models import UserManager
from django.db import models
from django.db.models import Case, F, Q, TextField, Value, When
from django.db.models.functions import Concat
from django.db.models.functions.comparison import Coalesce


class UserQuerySet(models.QuerySet):
    """Selection helpers which the user manager exposes as its own methods"""

    def with_meta(self):
        return self.annotate(
            group_count=Coalesce(models.Count("groups"), 0)
        )

    def with_string_representation(self):
        """Annotate the display string which ``User.__str__`` answers.

        The pickers of the frontend render and sort by that string, so the api
        has to order users by it, and the annotation mirrors the model: the
        name in parentheses only appears when there is one, and a name of a
        single part is not padded with a space (#1035).
        """
        return self.annotate(
            string_representation=Case(
                When(Q(first_name="") & Q(last_name=""), then=F("username")),
                When(first_name="", then=Concat(
                    F("username"), Value(" ("), F("last_name"), Value(")"))),
                When(last_name="", then=Concat(
                    F("username"), Value(" ("), F("first_name"), Value(")"))),
                default=Concat(
                    F("username"), Value(" ("),
                    F("first_name"), Value(" "), F("last_name"), Value(")")),
                output_field=TextField()))


class CustomUserManager(UserManager.from_queryset(UserQuerySet)):
    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: username})
