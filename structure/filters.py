import django_filters
from django.forms import TextInput, CheckboxInput, ChoiceField, CharField

from structure.models import Group, Organization


class GroupFilter(django_filters.FilterSet):
    # gn = groups name
    gn = django_filters.CharFilter(field_name='name',
                                   lookup_expr='icontains',
                                   widget=TextInput(attrs={'class': 'mr-1', }))
    # gd = groups description
    gd = django_filters.CharFilter(field_name='description',
                                   lookup_expr='icontains',
                                   widget=TextInput(attrs={'class': 'mr-1', }))
    # go = groups organization
    go = django_filters.CharFilter(field_name='organization',
                                   lookup_expr='organization_name__icontains',
                                   widget=TextInput(attrs={'class': 'mr-1',
                                                           'placeholder': 'Organization contains'}))

    class Meta:
        model = Group
        fields = []


class OrganizationFilter(django_filters.FilterSet):
    OIAG_CHOICES = (
        (False, 'Only real organizations'),
        (True, 'Only not real organizations'),
    )

    # on = Organization name
    on = django_filters.CharFilter(field_name='organization_name',
                                   label='Name contains',
                                   lookup_expr='icontains',
                                   widget=TextInput(attrs={'class': 'mr-1', },))
    # od = Organizationdescription
    od = django_filters.CharFilter(field_name='description',
                                   lookup_expr='icontains',
                                   widget=TextInput(attrs={'class': 'mr-1', },))
    # oiag = Organization is_auto_generated
    oiag = django_filters.ChoiceFilter(field_name='is_auto_generated',
                                       choices=OIAG_CHOICES,
                                       empty_label='All organizations', null_value=False)

    class Meta:
        model = Organization
        fields = []
