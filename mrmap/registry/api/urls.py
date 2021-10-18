from rest_framework.routers import DefaultRouter
from registry.api.views.mapcontext import MapContextViewSet

app_name = 'registry'

registry_api_router = DefaultRouter()
registry_api_router.register(app_name + '/mapcontexts', MapContextViewSet, basename='mapcontext_api_router')
