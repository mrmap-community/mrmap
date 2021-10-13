from rest_framework.routers import DefaultRouter

from registry.api.views.mapcontext import MapContextViewSet

mapcontext_api_router = DefaultRouter()
mapcontext_api_router.register('registry/mapcontext/', MapContextViewSet, base_name='mapcontext_api_router')

