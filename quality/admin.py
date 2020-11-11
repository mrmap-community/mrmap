"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.contrib import admin

from quality.models import ConformityCheckConfigurationExternal, \
    ConformityCheckConfigurationInternal, Rule, RuleSet, \
    ConformityCheckRun


class ConformityCheckConfigurationExternalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'metadata_types')


class ConformityCheckConfigurationInternalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'metadata_types')
    filter_horizontal = ['mandatory_rule_sets', 'optional_rule_sets']


class RuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'field_name', 'property', 'operator')


class RuleSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    filter_horizontal = ['rules']


# TODO remove this. This is just for testing purposes
class ConformityCheckRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'time_start', 'time_stop', 'passed')


admin.site.register(ConformityCheckConfigurationExternal,
                    ConformityCheckConfigurationExternalAdmin)
admin.site.register(ConformityCheckConfigurationInternal,
                    ConformityCheckConfigurationInternalAdmin)
admin.site.register(Rule, RuleAdmin)
admin.site.register(RuleSet, RuleSetAdmin)
admin.site.register(ConformityCheckRun, ConformityCheckRunAdmin)
