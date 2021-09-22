from django.urls import path
from acls.views import *

app_name = 'acls'
urlpatterns = [
    # acls
    path('acls', AccessControlListTableView.as_view(), name='accesscontrollist_overview'),
    path('acls/<pk>', AccessControlListDetailView.as_view(), name='accesscontrollist_view'),
    path('acls/<pk>/change', AccessControlListUpdateView.as_view(), name='accesscontrollist_change'),
]

