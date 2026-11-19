"""``GET /api/accounts/effective-permissions`` - a decision, down to its grant.

#734 answers *whether* an account may do something. #741 asks the next
question, the one support and an auditor ask over a shoulder: **why** - which
layer decided, and which concrete grant is behind it. The answer comes from
:func:`extras.permissions.explain`, which walks the same axes as
``allowed()`` in the same order and only looks rows up where an axis answered
yes; there is no second implementation of the decision here to drift from the
first.

Query parameters:

``model``
    the model to ask about, as ``registry.webmapservice``, ``registry.WebMapService``
    or a bare ``WebMapService`` when the name belongs to one model.
``object``
    the primary key of the row to ask about.
``perm``
    optional; one permission to answer instead of the object permissions the
    model offers (``view``, ``change``, ``delete``). Accepted as the codename or
    as ``app_label.codename``.

The answer is about **the calling account's own** rights over that object: the
endpoint takes no ``user`` parameter, because "whose rights?" is a question
whose answer is who-holds-what. Whoever asks about somebody else's rights is
the audit duty of :func:`accounts.permissions.may_audit_permissions_of`, which
this view asks beside the answer itself - see :meth:`EffectivePermissionsView.get`.

The response is plain JSON rather than a JSON:API resource: the answer is not a
row of a table but a decision about one, and naming it a resource would promise
a type, an id and a list route for something which has none of them and must
never be listable.
"""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.utils import (OpenApiParameter, OpenApiTypes,
                                   extend_schema)
from extras.permissions import explain, object_organization
from rest_framework.exceptions import (NotFound, PermissionDenied,
                                       ValidationError)
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import may_audit_permissions_of

#: the verbs an account is normally asked about over one object; a model which
#: offers fewer simply gets fewer answers. These are verbs and not codenames:
#: django names the permission row of a verb after the model, so
#: ``_codenames_or_400`` builds ``<verb>_<model_name>`` from them
OBJECT_VERBS = ("view", "change", "delete")

MODEL_PARAMETER = OpenApiParameter(
    name="model",
    description="the model to ask about: 'registry.webmapservice' or "
                "'WebMapService'",
    required=True,
    type=str,
)
OBJECT_PARAMETER = OpenApiParameter(
    name="object",
    description="the primary key of the object to ask about",
    required=True,
    type=str,
)
PERM_PARAMETER = OpenApiParameter(
    name="perm",
    description="one permission codename to answer instead of the object "
                "permissions of the model",
    required=False,
    type=str,
)


def _model_or_400(value) -> type:
    """The model ``value`` names, or a 400 naming what it could not resolve.

    Both spellings an operator has to hand are accepted: the dotted
    ``app_label.model_name`` of a permission, and the class name read off a
    screen. A bare name which belongs to two apps is refused rather than
    guessed - explaining the wrong model is worse than answering nothing.
    """
    if not value:
        raise ValidationError("The 'model' parameter is required.")
    if "." in value:
        app_label, _, model_name = value.partition(".")
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            raise ValidationError(
                f"No model '{app_label}.{model_name}' in this instance.")
    matches = [model for model in apps.get_models()
               if model._meta.model_name == value.lower()
               or model.__name__ == value]
    if len(matches) == 1:
        return matches[0]
    raise ValidationError(
        f"'{value}' names {len(matches)} models; name the app as "
        f"'app_label.{value}'.")


def _object_or_404(model, value):
    """The row of ``model`` with ``pk`` ``value``, or 404 / 400.

    A primary key which cannot be read as the model's own kind of key is a bad
    request, not a missing object: the caller wrote the wrong model, and the
    answer says so instead of pretending the row never existed.
    """
    if not value:
        raise ValidationError("The 'object' parameter is required.")
    try:
        obj = model.objects.filter(pk=value).first()
    except (DjangoValidationError, ValueError, TypeError):
        raise ValidationError(
            f"'{value}' is not a valid id of a {model.__name__}.")
    if obj is None:
        raise NotFound(
            f"No {model._meta.verbose_name} with this id.")
    return obj


def _codenames_or_400(model, perm) -> list:
    """The permission codenames of ``model`` to answer.

    Asked of the ``Permission`` rows and not of the model's ``Meta``: an answer
    must name a permission the instance actually has, and a codename which
    belongs to another model is a bad request rather than an empty answer.

    Without ``perm`` the object permissions of the model are named from the
    verbs and the model's own name, because that is how the rows are called:
    ``view_webmapservice``. A custom codename of the model -
    ``can_publish_for_organization`` - does not follow that shape and is not
    part of the default answer: a caller who wants to know about such a right
    names it, which is what ``perm`` is for.
    """
    content_type = ContentType.objects.get_for_model(model)
    wanted = perm.rsplit(".", 1)[-1] if perm else None
    defaults = [f"{verb}_{model._meta.model_name}" for verb in OBJECT_VERBS]
    codenames = list(
        content_type.permission_set
        .filter(codename__in=[wanted] if wanted else defaults)
        .order_by("codename")
        .values_list("codename", flat=True))
    if codenames:
        return codenames
    if wanted:
        raise ValidationError(
            f"The model '{model._meta.label}' has no permission '{perm}'.")
    raise ValidationError(
        f"The model '{model._meta.label}' has no object permission among "
        f"{', '.join(defaults)}.")


class EffectivePermissionsView(APIView):
    """The explain answer of #741, about the calling account.

    The answer is composed of the grants behind
    :func:`extras.permissions.explain` and not of one model row, which is why
    it renders as plain JSON and is reached by a ``path()`` in
    ``accounts/urls.py`` beside ``who-am-i`` - there is no resource to register
    here, and a list route over every object of a model is exactly what this
    endpoint must never become.

    Plain JSON has one consequence a caller learns here rather than in a 406:
    a request whose ``Accept`` names the JSON:API media type is refused, the
    same split ``POST /api/auth/session`` of #738 makes. The shape of an audit
    answer is not allowed to depend on a header, so the media type is pinned
    and not negotiated between two renderers.
    """

    renderer_classes = [JSONRenderer]
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    # the answer is spelled as an object and not guessed: a view without a
    # serializer makes drf-spectacular report an error and drop the endpoint
    # from the schema, which would hide the answer from the api docs of #741
    @extend_schema(
        operation_id="retrieve_effective_permissions",
        parameters=[MODEL_PARAMETER, OBJECT_PARAMETER, PERM_PARAMETER],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT,
                   403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        summary="Why the calling account may or may not touch one",
    )
    def get(self, request, *args, **kwargs) -> Response:
        model = _model_or_400(request.query_params.get("model"))
        obj = _object_or_404(model, request.query_params.get("object"))
        codenames = _codenames_or_400(
            model, request.query_params.get("perm"))

        app_label, _, _ = model._meta.label.partition(".")
        answers = [
            explain(request.user, f"{app_label}.{codename}", obj)
            for codename in codenames]

        # Two gates, and either opens the answer. The caller who *is* allowed
        # something over this object has a stake in the answer about their own
        # rights - nothing is disclosed which their request does not already
        # let them exercise. The caller who is refused is answered for by the
        # audit duty: a platform holder, the superuser, or the administrator of
        # the organization the object belongs to. Nobody else: an unrelated
        # account learns nothing about who holds what (#741's AC2).
        if not any(answer["allowed"] for answer in answers) \
                and not may_audit_permissions_of(request.user, obj):
            raise PermissionDenied(
                "You hold nothing over this object and do not audit its "
                "organization.")

        organization = object_organization(obj)
        return Response({
            "model": model._meta.label_lower,
            "object": str(obj.pk),
            "string_representation": str(obj),
            "organization": str(organization) if organization else None,
            "as_of": timezone.now().isoformat(),
            "answers": answers,
        })
