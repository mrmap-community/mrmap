# Create your views here.
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from rest_framework.authtoken.models import Token
from MrMap.responses import DefaultContext
from api.forms import TokenForm
from structure.permissionEnums import PermissionEnum


def menu_view(request: HttpRequest):
    """ The API menu view where settings for the remote access can be set.

    Args:
        request (HttpRequest): The incoming request
    Returns:
         rendered view
    """
    template = "views/api_menu.html"
    token_form = TokenForm(request.POST)
    user = request.user

    if not user.is_authenticated:
        return redirect("login")

    # Get user token
    try:
        token = Token.objects.get(
            user=user
        )
    except ObjectDoesNotExist:
        # User has no token yet
        token = None

    if token is not None:
        token_form = TokenForm(instance=token)

    token_form.action_url = reverse("api:generate-token")
    params = {
        "form": token_form,
    }
    default_context = DefaultContext(request, params, user)
    return render(request, template, default_context.get_context())


@permission_required(PermissionEnum.CAN_GENERATE_API_TOKEN.value, raise_exception=True)
def generate_token(request: HttpRequest):
    """ Generates a token for the user.

    Returns after finished work back to the menu page

    Args:
        request (HttpRequest): The incoming request
    Returns:
         A redirect to a view
    """
    if request.method == "POST":
        user = request.user
        # Get user token
        try:
            token = Token.objects.get(
                user=user
            )
        except ObjectDoesNotExist:
            # User has no token yet
            token = None

        # Remove the given key.
        # Otherwise the is_valid() would fail, since the key for this user could already exists.
        # We are only interested in the csrf token validation.
        post_dict = request.POST.dict()
        post_dict["key"] = ""
        token_form = TokenForm(post_dict)

        if not token_form.is_valid():
            return HttpResponse(status=403)

        # Generate new access token, old token can not be reused, must be deleted
        if token is not None:
            token.delete()
        token = Token(user=user)
        token.save()

    # Redirect user directly to the same page. Why?
    # This way, we make sure the user does not re-generate another token accidentally by pressing F5 or reload,
    # or whatever. We force the GET way.
    return redirect("api:menu")

