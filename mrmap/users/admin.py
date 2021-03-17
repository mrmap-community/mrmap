from django.contrib import admin
from users.models import Subscription


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'notify_on_update', 'notify_on_metadata_edit', 'notify_on_access_edit', 'created_on')
    readonly_fields = ('created_on',)


admin.site.register(Subscription, SubscriptionAdmin)
