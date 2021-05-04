from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django_filters.views import FilterView
from MrMap.views import CustomSingleTableMixin
from structure.tables.tables import MrMapUserTable


class UserTableView(LoginRequiredMixin, CustomSingleTableMixin, FilterView):
    model = get_user_model()
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'groups__name': ['icontains']}
