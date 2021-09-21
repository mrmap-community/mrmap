"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from extras.models import CommonInfo, GenericModelMixin
from extras.polymorphic_fk import PolymorphicForeignKey
from quality.enums import RuleFieldNameEnum, RulePropertyEnum, \
    RuleOperatorEnum, \
    ConformityTypeEnum, ReportType
from quality.managers import ConformityCheckRunManager, ConformityCheckConfigurationManager
from registry.models import Service, Layer, FeatureType
from registry.models.metadata import DatasetMetadata, ServiceMetadata, LayerMetadata, FeatureTypeMetadata


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

    def is_allowed_type(self, metadata):
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


class ConformityCheckRun(CommonInfo, GenericModelMixin):
    """
    Model holding the relation of a resource to the results of a check.
    """
    config = models.ForeignKey(ConformityCheckConfiguration, on_delete=models.CASCADE)
    passed = models.BooleanField(blank=True, null=True)
    report = models.TextField(blank=True, null=True)
    report_type = models.TextField(
        choices=ReportType.as_choices(drop_empty_choice=True))

    # polymorphic fk: only one of the following resource references should be used
    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("service"),
                                help_text=_("the service targeted by this check"))
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("layer"),
                              help_text=_("the layer targeted by this check"))
    feature_type = models.ForeignKey(FeatureType, on_delete=models.CASCADE, null=True, blank=True,
                                     verbose_name=_("feature type"),
                                     help_text=_("the feature type targeted by this check"))
    dataset_metadata = models.ForeignKey(DatasetMetadata, on_delete=models.CASCADE, null=True, blank=True,
                                         verbose_name=_("dataset metadata"),
                                         help_text=_("the dataset metadata targeted by this check"))
    service_metadata = models.ForeignKey(ServiceMetadata, on_delete=models.CASCADE, null=True, blank=True,
                                         verbose_name=_("service metadata"),
                                         help_text=_("the service metadata targeted by this check"))
    layer_metadata = models.ForeignKey(LayerMetadata, on_delete=models.CASCADE, null=True, blank=True,
                                       verbose_name=_("layer metadata"),
                                       help_text=_("the layer metadata targeted by this check"))
    feature_type_metadata = models.ForeignKey(FeatureTypeMetadata, on_delete=models.CASCADE, null=True, blank=True,
                                              verbose_name=_("feature type metadata"),
                                              help_text=_("the feature type metadata targeted by this check"))

    _resource = PolymorphicForeignKey('service', 'layer', 'feature_type', 'dataset_metadata', 'service_metadata',
                                      'layer_metadata', 'feature_type_metadata')

    objects = ConformityCheckRunManager()

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "-created_at"

    @property
    def resource(self):
        return self._resource.get_target(self)

    @property
    def resource_type(self):
        return self._resource.get_target(self).__class__.__name__

    def clean(self):
        self._resource.validate(self)

    def get_report_url(self):
        return f"{reverse('quality:conformity_check_run_report', kwargs={'pk': self.pk})}"

    def is_running(self):
        return self.passed is None

    @classmethod
    def get_validate_url(cls, resource):
        if isinstance(resource, Service):
            return cls.get_add_url() + f"?service={resource.pk}"
        if isinstance(resource, Layer):
            return cls.get_add_url() + f"?layer={resource.pk}"
        if isinstance(resource, FeatureType):
            return cls.get_add_url() + f"?feature_type={resource.pk}"
        if isinstance(resource, DatasetMetadata):
            return cls.get_add_url() + f"?dataset_metadata={resource.pk}"
        if isinstance(resource, ServiceMetadata):
            return cls.get_add_url() + f"?service_metadata={resource.pk}"
        if isinstance(resource, LayerMetadata):
            return cls.get_add_url() + f"?layer_metadata={resource.pk}"
        if isinstance(resource, FeatureTypeMetadata):
            return cls.get_add_url() + f"?feature_type_metadata={resource.pk}"
        return None
