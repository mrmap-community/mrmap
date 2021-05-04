from model_bakery.recipe import Recipe
from model_bakery import seq
from users.models import MrMapUser

user = Recipe(
    MrMapUser,
    username=seq("user"),
    email="god@heaven.va",
    password=make_password("354Dez25!"),
    is_active=True,
)
