from rest_framework.fields import CharField
from rest_framework_json_api.serializers import Serializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer as JwTTokenObtainPairSerializer


class TokenObtainPairSerializer(Serializer, JwTTokenObtainPairSerializer):
    class Meta:
        resource_name = 'Token'


class TokenSerializer(Serializer):
    access = CharField()
    refresh = CharField()

    class Meta:
        resource_name = 'Token'
