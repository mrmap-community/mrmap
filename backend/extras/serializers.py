from django.conf import settings
from django.contrib.auth import get_user_model
from guardian.core import ObjectPermissionChecker
from rest_framework_json_api.relations import \
    SerializerMethodResourceRelatedField
from rest_framework_json_api.serializers import (ModelSerializer,
                                                 SerializerMethodField)


class ObjectPermissionCheckerSerializer(ModelSerializer):
    is_accessible = SerializerMethodField()

    class Meta:
        abstract = True

    def get_perm_checker(self):
        perm_checker = self.context.get('perm_checker', None)
        if not perm_checker and 'request' in self.context:
            # fallback with slow solution if no perm_checker is in the context
            perm_checker = ObjectPermissionChecker(
                user_or_group=self.context['request'].user)
            settings.ROOT_LOGGER.warning(
                "slow handling of object permissions detected. Optimize your view by adding a permchecker in your view.")
        return perm_checker

    def get_is_accessible(self, obj):
        perm_checker = self.get_perm_checker()
        return perm_checker.has_perm(f'view_{obj._meta.model_name}', obj)


class HistoryInformationSerializer(ModelSerializer):
    created_at = SerializerMethodField()
    last_modified_at = SerializerMethodField()

    created_by = SerializerMethodResourceRelatedField(
        model=get_user_model(),
        required=False,
        # related_link_view_name='accounts:user-detail',
        # related_link_url_kwarg='pk',
    )
    last_modified_by = SerializerMethodResourceRelatedField(
        model=get_user_model(),
        required=False,
    )

    class Meta:
        abstract = True

    def get_created_at(self, instance):
        return instance.first_history[0].history_date if instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_at(self, instance):
        return instance.last_history[0].history_date if instance.last_history and len(instance.last_history) == 1 else None

    def get_created_by(self, instance):
        return instance.first_history[0].history_user if instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_by(self, instance):
        return instance.last_history[0].history_user if instance.last_history and len(instance.last_history) == 1 else None
