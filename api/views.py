from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, permissions

from api.serializers import ServiceSerializer, LayerSerializer
from service.models import Service, Layer


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    queryset = Service.objects.filter(is_root=True)

class LayerViewSet(viewsets.ModelViewSet):
    serializer_class = LayerSerializer
    queryset = Layer.objects.all()
