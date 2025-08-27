import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.functions import datetime
from django.urls import resolve
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from guardian.core import ObjectPermissionChecker
from rest_framework_json_api.relations import \
    SerializerMethodResourceRelatedField
from rest_framework_json_api.serializers import (ModelSerializer,
                                                 SerializerMethodField)


class StringRepresentationSerializer(ModelSerializer):
    string_representation = SerializerMethodField(read_only=True)

    class Meta:
        abstract = True

    def get_string_representation(self, obj) -> str:
        return obj.__str__()


# TODO: Split this into two classes one which implements the get_perm_checker function and one which implements the is_accessible field
class ObjectPermissionCheckerSerializer(ModelSerializer):
    is_accessible = SerializerMethodField(read_only=True)

    class Meta:
        abstract = True

    def get_perm_checker(self):
        perm_checker = self.context.get('perm_checker', None)
        if not perm_checker and 'request' in self.context:
            # fallback with slow solution if no perm_checker is in the context
            perm_checker = ObjectPermissionChecker(
                user_or_group=self.context['request'].user)

            extra = {}
            request = self.context.get("request")
            if request:
                view, _, _ = resolve(request.path)
                extra.update(
                    {
                        "structured_data": {
                            "metaSDID@django": {
                                "view_name": view
                            }
                        }
                    }
                )

            settings.ROOT_LOGGER.warning(
                msg="slow handling of object permissions detected. Optimize your view by adding a permchecker.",
                extra=extra
            )
        return perm_checker

    def get_is_accessible(self, obj) -> bool:
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

    def get_created_at(self, instance) -> datetime:
        return instance.first_history[0].history_date if hasattr(instance, 'first_history') and instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_at(self, instance) -> datetime:
        return instance.last_history[0].history_date if hasattr(instance, 'last_history') and instance.last_history and len(instance.last_history) == 1 else None

    def get_created_by(self, instance):
        return instance.first_history[0].history_user if hasattr(instance, 'first_history') and instance.first_history and len(instance.first_history) == 1 else None

    def get_last_modified_by(self, instance):
        return instance.last_history[0].history_user if hasattr(instance, 'last_history') and instance.last_history and len(instance.last_history) == 1 else None


class SystemInfoSerializerMixin:
    def get_root_meta(self, resource, many):

        return {
            "system_time": timezone.localtime(timezone.now())
        }


class TimeUntilNextRunMixin:
    time_until_next_run = SerializerMethodField(label=_("time until next run"))

    def get_time_until_next_run(self, obj):
        # aktuelle lokale Zeit
        now_local = timezone.localtime(timezone.now())

        # Zeitzone aus Crontab (oder fallback UTC)
        tz = obj.crontab.timezone or pytz.UTC

        # Jetzt in Crontab-Zeitzone konvertieren
        now_tz = now_local.astimezone(tz)

        schedule = obj.crontab.schedule

        remaining = schedule.remaining_estimate(now_tz)
        if remaining is None:
            return "unbekannt"

        total_seconds = int(remaining.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}min")
        parts.append(f"{seconds}s")

        return " ".join(parts)
        return " ".join(parts)
