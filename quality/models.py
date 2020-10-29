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

    def __str__(self):
        return self.name


class ConformityCheckConfigurationExternal(ConformityCheckConfiguration):
    """
    Model holding the configs for an external conformity check.
    """
    # TODO BKG already includes the metadata record in the configuration
    #          so the url triggering the test is not generic but specific for
    #          exactly one test case
    # external_url = models.URLField(max_length=1000)
    parameter_map = models.JSONField()
    response_map = models.JSONField()

    @staticmethod
    def is_external() -> bool:
        return True

    @staticmethod
    def is_internal() -> bool:
        return False


class Rule(models.Model):
    """
    Model holding the definition of a single rule.
    """
    name = models.CharField(max_length=1000)
    field_name = models.TextField(choices=RuleFieldNameEnum.as_choices(drop_empty_choice=True))
    property = models.TextField(choices=RulePropertyEnum.as_choices(drop_empty_choice=True))
    operator = models.TextField(choices=RuleOperatorEnum.as_choices(drop_empty_choice=True))
    # TODO ask if there shouldn't be any value field to compare to

    def __str__(self):
        return self.name


class RuleSet(models.Model):
    """
    Model grouping rules and holding the result of a rule check run.
    """
    name = models.CharField(max_length=1000)
    rules = models.ManyToManyField(Rule, related_name="rule_set")

    def __str__(self):
        return self.name


class ConformityCheckConfigurationInternal(ConformityCheckConfiguration):
    """
    Model holding the configs for an internal conformity check.
    """
    mandatory_rule_sets = models.ManyToManyField(RuleSet, related_name="mandatory_rule_sets")
    optional_rule_sets = models.ManyToManyField(RuleSet, related_name="optional_rule_sets", blank=True, null=True)

    @staticmethod
    def is_internal() -> bool:
        return True

    @staticmethod
    def is_external() -> bool:
        return False


class ConformityCheckRun(models.Model):
    """
    Model holding the relation of a metadata record to the results of a check.
    """
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    # TODO check if this actually works, i.e. can we properly retrieve the internal/external config?
    conformity_check_configuration = models.ForeignKey(ConformityCheckConfiguration, on_delete=models.CASCADE)
    # TODO Proposal as BKG connects Metadata record in configuration
    external_url = models.URLField(max_length=1000)
    # TODO check if this should actually be set to auto_now_add
    time_start = models.DateTimeField(auto_now_add=True)
    time_stop = models.DateTimeField(blank=True, null=True)
    errors = models.TextField(blank=True, null=True)
    passed = models.BooleanField(blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)
