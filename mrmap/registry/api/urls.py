from rest_framework.routers import DefaultRouter
from registry.api.views.mapcontext import MapContextViewSet
from registry.api.views.service import ServiceViewSet

app_name = 'registry'

registry_api_router = DefaultRouter()
registry_api_router.register(app_name + '/mapcontexts', MapContextViewSet, basename='mapcontext_api_router')
registry_api_router.register(app_name + '/services', ServiceViewSet, basename='service_api_router')
