"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.contrib import admin

from quality.models import ConformityCheckConfigurationExternal, ConformityCheckConfigurationInternal, Rule, RuleSet

admin.site.register(ConformityCheckConfigurationExternal)
admin.site.register(ConformityCheckConfigurationInternal)
admin.site.register(Rule)
admin.site.register(RuleSet)
