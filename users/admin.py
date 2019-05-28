from django.contrib import admin

# Register your models here.
from users.models import User, UserActivation


class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'person_name', 'username', 'last_login']

class UserActivationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user']

admin.site.register(User, UserAdmin)
admin.site.register(UserActivation, UserActivationAdmin)