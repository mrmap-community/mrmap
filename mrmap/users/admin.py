from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from users.models import Subscription, MrMapUser


class MrMapUserAdmin(UserAdmin):
    # We want to use the UserAdmin interface, which provides great support for security related settings.
    # But it won't show all the fields, that exist in our custom User class.
    # Therefore we need to reference them like this.
    model = MrMapUser
    fieldsets = (
            ("User details",
             {
                 'fields': (
                     'confirmed_newsletter',
                     'confirmed_survey',
                     'confirmed_dsgvo',
                 )
             }
             ),
    ) + UserAdmin.fieldsets
    readonly_fields = (
        "confirmed_dsgvo",
        "user_permissions",  # Prevent accidental changes on user_permissions (inherited from AbstractUser) since groups manage permissions!
    )


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'notify_on_update', 'notify_on_metadata_edit', 'notify_on_access_edit', 'created_on')
    readonly_fields = ('created_on',)


admin.site.register(MrMapUser, MrMapUserAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
