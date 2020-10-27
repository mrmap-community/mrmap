"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db import models

from quality.enums import RuleFieldNameEnum, RulePropertyEnum, RuleOperatorEnum
from service.models import Metadata


class ConformityCheckConfiguration(models.Model):
    """
    Base model for ConformityCheckConfiguration classes.
    """
    name = models.CharField(max_length=1000)
    metadata_types = models.TextField()


class ConformityCheckConfigurationExternal(ConformityCheckConfiguration):
    """
    Model holding the configs for an external conformity check.
    """
    external_url = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    parameter_map = models.JSONField()
    response_map = models.JSONField()


class Rule(models.Model):
    """
    Model holding the definition of a single rule.
    """
    name = models.CharField(max_length=1000)
    field_name = models.TextField(choices=RuleFieldNameEnum.as_choices(drop_empty_choice=True))
    property = models.TextField(choices=RulePropertyEnum.as_choices(drop_empty_choice=True))
    operator = models.TextField(choices=RuleOperatorEnum.as_choices(drop_empty_choice=True))
    # TODO ask if there shouldn't be any value field to compare to


class RuleSet(models.Model):
    """
    Model grouping rules and holding the result of a rule check run.
    """
    name = models.CharField(max_length=1000)
    rules = models.ManyToManyField(Rule, related_name="rule_set")


class ConformityCheckConfigurationInternal(ConformityCheckConfiguration):
    """
    Model holding the configs for an internal conformity check.
    """
    mandatory_rule_sets = models.ManyToManyField(RuleSet, related_name="mandatory_rule_sets")
    optional_rule_sets = models.ManyToManyField(RuleSet, related_name="optional_rule_sets")


class ConformityCheckRun(models.Model):
    """
    Model holding the relation of a metadata record to the results of a check.
    """
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    conformity_check_configuration = models.ForeignKey(ConformityCheckConfiguration, on_delete=models.CASCADE)
    time_start = models.DateTimeField(auto_now_add=True)
    time_stop = models.DateTimeField(auto_now_add=True)
    errors = models.TextField()
    passed = models.BooleanField()
    additional_info = models.TextField()
    result = models.TextField()
