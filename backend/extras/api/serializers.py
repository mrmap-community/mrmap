from collections import OrderedDict
from rest_framework.serializers import ModelSerializer


class NonNullModelSerializer(ModelSerializer):
    def to_representation(self, instance):
        result = super(NonNullModelSerializer, self).to_representation(instance)
        return OrderedDict([(key, result[key]) for key in result if result[key] is not None])


class ObjectAccessSerializer(ModelSerializer):
    def to_representation(self, instance):
        # get the original representation
        result = super().to_representation(instance)

        # get the permission checker
        checker = self.context.get('permission_checker')

        # set the accessible flag to true case the condition is verified
        if checker and checker.has_perm(f'{instance._meta.app_label}.view_{instance._meta.object_name}', instance):
            result['accessible'] = True
        # set the accessible flag to false case the condition is not verified
        else:
            result['accessible'] = False
        return result
