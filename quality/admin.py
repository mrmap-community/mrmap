"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.contrib import admin

from quality.models import ConformityCheckConfigurationExternal, ConformityCheckConfigurationInternal, Rule, RuleSet, \
    ConformityCheckRun


class ConformityCheckConfigurationExternalAdmin(admin.ModelAdmin):
    list_display = ('id',)


class ConformityCheckConfigurationInternalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'metadata_types')
    filter_horizontal = ['mandatory_rule_sets', 'optional_rule_sets']


class RuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'field_name', 'property', 'operator')


class RuleSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


# TODO remove this. This is just for testing purposes
class ConformityCheckRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'metadata', 'passed')
    # metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    # conformity_check_configuration = models.ForeignKey(ConformityCheckConfiguration, on_delete=models.CASCADE)
    # time_start = models.DateTimeField(blank=True, null=True)
    # time_stop = models.DateTimeField(blank=True, null=True)
    # errors = models.TextField(blank=True, null=True)
    # passed = models.BooleanField(blank=True, null=True)
    # additional_info = models.TextField(blank=True, null=True)
    # result = models.TextField(blank=True, null=True)


admin.site.register(ConformityCheckConfigurationExternal, ConformityCheckConfigurationExternalAdmin)
admin.site.register(ConformityCheckConfigurationInternal, ConformityCheckConfigurationInternalAdmin)
admin.site.register(Rule, RuleAdmin)
admin.site.register(RuleSet, RuleSetAdmin)
# TODO remove this. This is just for testing purposes
admin.site.register(ConformityCheckRun, ConformityCheckRunAdmin)
