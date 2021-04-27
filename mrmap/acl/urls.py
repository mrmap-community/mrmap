from django.urls import path
from acl.views import *

app_name = 'acl'
urlpatterns = [
    # acls
    path('', AccessControlListTableView.as_view(), name='accesscontrollist_overview'),
    #path('acls/<pk>', OrganizationDetailView.as_view(), name='organization_view'),
    path('create', AccessControlListCreateView.as_view(), name='accesscontrollist_create'),
    path('<pk>/change', AccessControlListUpdateView.as_view(), name='accesscontrollist_change'),
]

