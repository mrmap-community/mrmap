"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db import models, transaction
from django.urls import reverse

from main.models import CommonInfo
from quality.enums import RuleFieldNameEnum, RulePropertyEnum, \
    RuleOperatorEnum, \
    ConformityTypeEnum
from quality.managers import ConformityCheckRunManager, ConformityCheckConfigurationManager
from resourceNew.models.metadata import DatasetMetadata


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

    def is_allowed_type(self, metadata: DatasetMetadata):
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
    external_url = models.URLField(max_length=1000, null=True)
    validation_target = models.TextField(max_length=1000, null=True)
    parameter_map = models.JSONField()
    polling_interval_seconds = models.IntegerField(default=5, blank=True,
                                                   null=False)
    polling_interval_seconds_max = models.IntegerField(default=5 * 60,
                                                       blank=True, null=False)


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
    threshold = models.TextField(null=True)

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


class ConformityCheckRun(CommonInfo):
    """
    Model holding the relation of a metadata record to the results of a check.
    """
    metadata = models.ForeignKey(DatasetMetadata, on_delete=models.CASCADE)
    # resource_type = models.TextField(blank=False, null=False)
    # resource_id = models.TextField(blank=False, null=False)

    conformity_check_configuration = models.ForeignKey(
        ConformityCheckConfiguration, on_delete=models.CASCADE)
    time_start = models.DateTimeField(auto_now_add=True)
    time_stop = models.DateTimeField(blank=True, null=True)
    passed = models.BooleanField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)

    objects = ConformityCheckRunManager()

    def get_absolute_url(self):
        return f'{reverse("quality:conformity_check_run_list")}?id={self.pk}'

    def is_running(self):
        return self.time_start is not None and self.passed is None

    def save(self, *args, **kwargs):
        adding = False
        if self._state.adding:
            adding = True
        super().save(*args, **kwargs)
        if adding:
            from quality.services import schedule_check_run
            transaction.on_commit(lambda: schedule_check_run(self))
