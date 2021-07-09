import django_filters
from dal import autocomplete
from django.contrib.auth import get_user_model

from resourceNew.enums.service import OGCOperationEnum
from resourceNew.models import Service
from resourceNew.models.security import AllowedOperation, ServiceAccessGroup, AnalyzedResponseLog, ExternalAuthentication
from django.utils.translation import gettext_lazy as _


class ExternalAuthenticationFilterSet(django_filters.FilterSet):
    class Meta:
        model = ExternalAuthentication
        fields = {
            "id": ["in"],
            "secured_service__id": ["in", ],
        }


class ServiceAccessGroupFilterSet(django_filters.FilterSet):
    class Meta:
        model = ServiceAccessGroup
        fields = {
            "id": ["in"],
            "name": ["icontains"],
            "description": ["icontains", ],
        }


class AllowedOperationFilterSet(django_filters.FilterSet):
    class Meta:
        model = AllowedOperation
        fields = {
            "id": ["in"],
            "description": ["icontains", ],
            "allowed_groups__id": ["in"],
            "secured_service__id": ["in"],
            "secured_layers__id": ["in"],
            "secured_feature_types__id": ["in"],
            "operations__operation": ["icontains"],
        }


class AnalyzedResponseLogFilterSet(django_filters.FilterSet):
    operation = django_filters.ChoiceFilter(label=_("Operation"),
                                            choices=OGCOperationEnum.as_choices(drop_empty_choice=True),
                                            field_name="response__request__url",
                                            lookup_expr="icontains",
                                            )
    user = django_filters.ModelMultipleChoiceFilter(label=_("User"),
                                                    field_name="response__request__user",
                                                    queryset=get_user_model().objects.all(),
                                                    widget=autocomplete.ModelSelect2Multiple(url="users.autocomplete:mrmapuser_ac",
                                                                                             attrs={
                                                                                                 "select2-containerCss": {
                                                                                                     #"height": "3em",
                                                                                                     "width": "auto",
                                                                                                 }
                                                                                             }))
    service = django_filters.ModelMultipleChoiceFilter(label=_("Service"),
                                                       field_name="response__request__service",
                                                       queryset=Service.objects.all(),
                                                       widget=autocomplete.ModelSelect2Multiple(url="resourceNew.autocomplete:service_ac"))

    class Meta:
        model = AnalyzedResponseLog
        fields = {
            "id": ["in"],
            #"response__request__service__id": ["in"],
            #"response__request__user__id": ["in"],
            #"operation__operation": ["in"],
            "response__request__url": ["icontains"],
            "entity_count": ["icontains"],
            "entity_total_count": ["icontains"],
            "entity_unit": ["exact"],
        }
