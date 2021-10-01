from django.urls import path
from users.autocompletes import users as user_views

app_name = "users.autocomplete"
urlpatterns = [

    # security models
    path('users/', user_views.MrMapUserAutocomplete.as_view(), name="mrmapuser_ac"),
]
