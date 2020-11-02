"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from datetime import datetime
from typing import Union

from quality.enums import RulePropertyEnum
from quality.models import ConformityCheckConfigurationInternal, \
    ConformityCheckConfigurationExternal, Rule, ConformityCheckRun, RuleSet
from service.models import Metadata


class Quality:

    def __init__(self, metadata: Metadata,
                 config: Union[
                     ConformityCheckConfigurationInternal,
                     ConformityCheckConfigurationExternal]):
        self.metadata = metadata
        self.config = config

    def run_check(self):
        if self.metadata is None:
            raise Exception("Could not check conformity. Metadata is None.")

        if self.config is None:
            raise Exception(
                "Could not check conformity. ConformityCheckConfiguration is "
                "None.")

        run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)

        if isinstance(self.config, ConformityCheckConfigurationInternal):
            self.check_internal(run)
        elif isinstance(self.config, ConformityCheckConfigurationExternal):
            self.check_external(run)
        else:
            raise Exception(
                "Could not check conformity. Invalid configuration.")

    def has_running_check(self) -> bool:
        """ Checks if the given metadata object has a non-finished
        ConformityCheckRun.

            Returns:
                True, if a non-finished ConformityCheckRun was found,
                false otherwise.
        """
        running_checks = ConformityCheckRun.objects.filter(
            metadata=self.metadata, passed__isnull=True).count()
        return running_checks != 0

    def check_internal(self, run: ConformityCheckRun):
        """ Runs the internal check for a given metadata object.

        Runs the mandatory and optional RuleSets of an internal check
        and updates the associated ConformityCheckRun accordingly.

        Args:
            run (ConformityCheckRun): The associated ConformityCheckRun.
        Returns:
            nothing

        """
        config = run.conformity_check_configuration

        mandatory_errors = []
        mandatory_success = True
        for rule_set in config.mandatory_rule_sets.all():
            mandatory_result = self.check_ruleset(rule_set)
            if not mandatory_result[0]:
                mandatory_success = False
            mandatory_errors.append(mandatory_result)

        optional_errors = []
        for rule_set in config.optional_rule_sets.all():
            optional_errors.append(self.check_ruleset(rule_set))

        run.passed = mandatory_success
        run.time_stop = datetime.now()
        # TODO check what ETF errors look like
        run.errors = self.merge_internal_errors(mandatory_errors,
                                                optional_errors)
        run.result = None  # TODO check what ETF results look like
        run.save()

    def check_external(self,
                       configuration: ConformityCheckConfigurationExternal):
        pass

    def merge_internal_errors(self, m_results, o_results):
        """ Merges the errors of the internal checks into a single result
        object.

        Takes the mandatory and optional results of the internal checks
        and merges them into a single result object that is harmonized
        to fit the structure of an external result object.

        Args:
            m_results (object[]): The results of the mandatory RuleSets.
            o_results (object[]): The results of the optional RuleSets.
        Returns:
            object: The merged and harmonized result object.
        """
        # TODO move to utility
        results = m_results + o_results

        errors = {'errors': []}
        for result_set in [r for r in results if not r[0]]:
            for result in result_set[1]:
                msg = f'Rule "{result[1]}" with condition "{result[2]}" ' \
                      f'evaluated to False'
                errors['errors'].append(msg)

        return errors['errors']

    def check_ruleset(self, ruleset: RuleSet):
        """ Evaluates all rules of a ruleset for the given metadata object.

        Evaluates for each rule in a ruleset, if it evaluates to true or false.
        A ruleset will be flagged as successful, if all rules evaluated to true.

        Args:
            ruleset (RuleSet): The RuleSet to evaluate.
        Returns:
            (bool, (bool, str)): The first value determines if the RuleSet
                                 evaluated to true or false.
                                 The second value holds the return values
                                 of self.check_rule for the failing rules.
        """
        # TODO should checks continue if a single check already failed?
        errors = []
        success = True
        for rule in ruleset.rules.all():
            passed, condition = self.check_rule(rule)
            if not passed:
                success = False
                errors.append((False, rule, condition))
        return success, errors

    def check_rule(self, rule: Rule):
        """ Evaluates a single rule for the given metadata object.

        Args:
            rule (Rule): The rule to evaluate.
        Returns:
            (bool, str): The first value determines if
                         the Rule evaluates to true or false.
                         The second value holds the condition as string.

        """
        prop = rule.property
        operator = rule.operator
        field = rule.field_name
        threshold = rule.threshold
        real_value = None

        if prop == RulePropertyEnum.LEN.value:
            attribute = self.metadata.__getattribute__(field)
            real_value = len(attribute)

        elif prop == RulePropertyEnum.COUNT.value:
            manager = self.metadata.__getattribute__(field)
            elements = manager.all()
            real_value = elements.count()

        # TODO Do we really want to cast threshold to String?
        #      Do we have to cast to different types?
        condition = str(real_value) + operator + str(threshold)

        return eval(condition, {'__builtins__': None}), condition
