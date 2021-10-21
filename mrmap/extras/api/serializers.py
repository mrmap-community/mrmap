import uuid
from collections import OrderedDict

from rest_framework.serializers import ModelSerializer


class NonNullModelSerializer(ModelSerializer):
    def to_representation(self, instance):
        result = super(NonNullModelSerializer, self).to_representation(instance)
        return OrderedDict([(key, result[key]) for key in result if result[key] is not None])


class ObjectAccessSerializer(ModelSerializer):
    def to_representation(self, instance):
        # get the original representation
        representation = super().to_representation(instance)
        # request = self.context.get('request')
        # view = self.context.get('view')
        # set the accessible flag to true case the condition is verified

        # TODO: how to verify current user permissions against required permission for view
        # if request and hasattr(request, "user") and request.user.get_user_permissions():
        if instance.id == uuid.UUID("c1a479ea-b8e1-4889-b2b6-856b82c30614"):
            representation['accessible'] = True
        # set the accessible flag to false case the condition is not verified and all other values to None
        # TODO: Confirm this behaviour
        else:
            representation['accessible'] = False
            for elem in representation:
                if elem != 'accessible':
                    representation[elem] = None
        return representation
