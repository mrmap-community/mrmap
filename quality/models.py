"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db import models

from quality.enums import RuleFieldNameEnum, RulePropertyEnum, \
    RuleOperatorEnum, \
    ConformityTypeEnum
from service.models import Metadata


class ConformityCheckConfigurationManager(models.Manager):
    """ Custom manager to extend ConformityCheckConfiguration methods """

    def get_for_metadata_type(self, metadata_type: str):
        """ Gets all configs that are allowed for the given metadata_type """
        return super().get_queryset().filter(
            metadata_types__contains=metadata_type)


class ConformityCheckConfiguration(models.Model):
    """
    Base model for ConformityCheckConfiguration classes.
    """
    name = models.CharField(max_length=1000)
    metadata_types = models.JSONField()
    conformity_type = models.TextField(
        choices=ConformityTypeEnum.as_choices(drop_empty_choice=True))

    objects = ConformityCheckConfigurationManager()

    def __str__(self):
        return self.name

    def is_allowed_type(self, metadata: Metadata):
        """ Checks if type of metadata is allowed for this config.

            Args:
                metadata (Metadata): The metadata object to check
            Returns:
                True, if metadata type is allowed for this config,
                False otherwise.
        """
        return metadata.metadata_type in self.metadata_types


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
    polling_interval_seconds = models.IntegerField(default=5, blank=True,
                                                   null=False)


class Rule(models.Model):
    """
    Model holding the definition of a single rule.
    """
    name = models.CharField(max_length=1000)
    field_name = models.TextField(
        choices=RuleFieldNameEnum.as_choices(drop_empty_choice=True))
    property = models.TextField(
        choices=RulePropertyEnum.as_choices(drop_empty_choice=True))
    operator = models.TextField(
        choices=RuleOperatorEnum.as_choices(drop_empty_choice=True))
    threshold = models.TextField()

    # TODO ask if there shouldn't be any value field to compare to

    def __str__(self):
        return self.name

    def as_dict(self):
        """Returns the model's field values as simple dictionary.

        This method should only be used for read-operations. E.g. to display
        the model contents as text or json.
        """
        return {
            "name": self.name,
            "field_name": self.field_name,
            "property": self.property,
            "operator": self.operator,
            "threshold": self.threshold
        }


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
    mandatory_rule_sets = models.ManyToManyField(RuleSet,
                                                 related_name="mandatory_rule_sets")
    optional_rule_sets = models.ManyToManyField(RuleSet,
                                                related_name="optional_rule_sets",
                                                blank=True)


class ConformityCheckRunManager(models.Manager):
    """ Custom manager to extend ConformityCheckRun methods """

    def has_running_check(self, metadata: Metadata):
        """ Checks if the given metadata object has a non-finished
        ConformityCheckRun.

            Returns:
                True, if a non-finished ConformityCheckRun was found,
                false otherwise.
        """
        running_checks = super().get_queryset().filter(
            metadata=metadata, passed__isnull=True).count()
        return running_checks != 0

    def get_latest_check(self, metadata: Metadata):
        check = super().get_queryset().filter(metadata=metadata).latest(
            'time_start')
        return check


class ConformityCheckRun(models.Model):
    """
    Model holding the relation of a metadata record to the results of a check.
    """
    metadata = models.ForeignKey(Metadata, on_delete=models.CASCADE)
    # TODO check if this actually works, i.e. can we properly retrieve the
    #  internal/external config?
    conformity_check_configuration = models.ForeignKey(
        ConformityCheckConfiguration, on_delete=models.CASCADE)
    # TODO Proposal as BKG connects Metadata record in configuration
    run_url = models.URLField(blank=True, null=True, max_length=1000)
    # TODO check if this should actually be set to auto_now_add
    time_start = models.DateTimeField(auto_now_add=True)
    time_stop = models.DateTimeField(blank=True, null=True)
    errors = models.TextField(blank=True, null=True)
    passed = models.BooleanField(blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)

    objects = ConformityCheckRunManager()

    def is_running(self):
        return self.time_stop is not None
