from django.urls import path
from acls import views as acl_views

app_name = 'acls'
urlpatterns = [
    # acls
    path('acls', acl_views.AccessControlListTableView.as_view(), name='accesscontrollist_overview'),
    path('acls/<pk>', acl_views.AccessControlListDetailView.as_view(), name='accesscontrollist_view'),
    path('acls/<pk>/change', acl_views.AccessControlListUpdateView.as_view(), name='accesscontrollist_change'),
]
