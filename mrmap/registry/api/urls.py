from rest_framework.routers import DefaultRouter
from registry.api.views import mapcontext as mapcontext_views
from registry.api.views import service as service_views

app_name = 'registry'

registry_api_router = DefaultRouter()
registry_api_router.register(app_name + '/mapcontexts', mapcontext_views.MapContextViewSet, basename="mapcontext")
registry_api_router.register(app_name + '/layers', service_views.LayerViewSet, basename='layer')
