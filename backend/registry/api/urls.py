# from registry.api.views import mapcontext as mapcontext_views
# from registry.api.views import metadata as metadata_views
from registry.api.views import service as service_views
from registry.api.views import jobs as jobs_views
from rest_framework_extensions.routers import ExtendedSimpleRouter
from django.urls import path

app_name = 'registry'

nested_api_router = ExtendedSimpleRouter()
(
    nested_api_router.register(r'wms', service_views.WebMapServiceViewSet, basename='wms')
                     .register(r'layers', service_views.LayerViewSet, basename='wms-layers', parents_query_lookups=['wms']),
    nested_api_router.register(r'wfs', service_views.WebFeatureServiceViewSet, basename='wfs')
                     .register(r'featuretypes', service_views.FeatureTypeViewSet, basename='wfs-featuretypes', parents_query_lookups=['wfs']),
    nested_api_router.register(r'jobs/register-wms-jobs', jobs_views.RegisterWebMapServiceViewSet, basename='register-wms-job'),
    nested_api_router.register(r'jobs/build-wms-tasks', jobs_views.BuildWebMapServiceTaskViewSet, basename='build-wms-task')
)

urlpatterns = nested_api_router.urls
urlpatterns.extend([
    path('wms/<pk>/relationships/<related_field>', service_views.WebMapServiceRelationshipView.as_view(), name='wms-relationships'),
    path('wfs/<pk>/relationships/<related_field>', service_views.WebFeatureServiceRelationshipView.as_view(), name='wfs-relationships')
])
