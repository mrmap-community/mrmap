"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
import json

from django.test import TestCase

from quality.enums import RuleFieldNameEnum, RulePropertyEnum, RuleOperatorEnum
from quality.models import ConformityCheckConfigurationInternal, Rule, RuleSet
from quality.plugins.internal import QualityInternal
from service.models import Metadata


class PluginInternalTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.metadata = Metadata.objects.create(
            title='Testmetadata',
        )
        cls.rule_fail = Rule.objects.create(
            name='Failing Rule',
            field_name=RuleFieldNameEnum.TITLE.value,
            property=RulePropertyEnum.LEN.value,
            operator=RuleOperatorEnum.LT.value,
            threshold=0
        )
        cls.rule_pass = Rule.objects.create(
            name='Passing Rule',
            field_name=RuleFieldNameEnum.TITLE.value,
            property=RulePropertyEnum.LEN.value,
            operator=RuleOperatorEnum.GT.value,
            threshold=0
        )
        cls.rule_set_pass = RuleSet.objects.create(
            name='Passing RuleSet',
        )
        cls.rule_set_pass.rules.add(cls.rule_pass)
        cls.rule_set_fail = RuleSet.objects.create(
            name='Failing RuleSet',
        )
        cls.rule_set_fail.rules.add(cls.rule_fail)
        cls.config = ConformityCheckConfigurationInternal.objects.create(
            metadata_types=json.dumps([])
        )

    def test_check_rule_fail(self):
        internal = QualityInternal(self.metadata, self.config)
        result = internal.check_rule(self.rule_fail)
        self.assertFalse(result['success'])

    def test_check_rule_pass(self):
        internal = QualityInternal(self.metadata, self.config)
        result = internal.check_rule(self.rule_pass)
        self.assertTrue(result['success'])

    def test_check_ruleset_fail(self):
        internal = QualityInternal(self.metadata, self.config)
        result = internal.check_ruleset(self.rule_set_fail)
        self.assertFalse(result['success'])

    def test_check_ruleset_pass(self):
        internal = QualityInternal(self.metadata, self.config)
        result = internal.check_ruleset(self.rule_set_pass)
        self.assertTrue(result['success'])

    def test_run_fail(self):
        # clone self.config
        config = self.config
        config.pk = None
        config.save()

        config.mandatory_rule_sets.add(self.rule_set_fail)
        config.save()

        internal = QualityInternal(self.metadata, config)
        run = internal.run()

        self.assertFalse(run.passed)

    def test_run_pass(self):
        # clone self.config
        config = self.config
        config.pk = None
        config.save()

        config.mandatory_rule_sets.add(self.rule_set_pass)
        config.save()

        internal = QualityInternal(self.metadata, config)
        run = internal.run()

        self.assertTrue(run.passed)

    def test_run_pass_with_optional_fail(self):
        # clone self.config
        config = self.config
        config.pk = None
        config.save()

        config.mandatory_rule_sets.add(self.rule_set_pass)
        config.optional_rule_sets.add(self.rule_set_fail)
        config.save()

        internal = QualityInternal(self.metadata, config)
        run = internal.run()

        self.assertTrue(run.passed)
