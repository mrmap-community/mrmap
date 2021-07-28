"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 02.11.20

"""
import json

from celery import states, current_task
from celery.result import AsyncResult
from django.utils import timezone

from quality.enums import RulePropertyEnum
from quality.models import RuleSet, Rule, \
    ConformityCheckConfigurationInternal, \
    ConformityCheckRun
from structure.celery_helper import runs_as_async_task


class QualityInternal:

    def __init__(self, run: ConformityCheckRun):
        base_config = run.config
        self.metadata = run.metadata
        self.config = ConformityCheckConfigurationInternal.objects.get(pk=base_config.pk)

        count = self.config.mandatory_rule_sets.all().count() + \
                self.config.optional_rule_sets.all().count()

        try:
            self.step_size = 80 / count
        except ZeroDivisionError:
            self.step_size = 80

    def run(self) -> ConformityCheckRun:
        """ Runs the internal check for a given metadata object.

        Runs the mandatory and optional RuleSets of an internal check
        and updates the associated ConformityCheckRun accordingly.

        Returns:
            The ConformityCheckRun instance

        """
        config = self.run.config

        results = {
            "success": True,
            "rule_sets": []
        }

        for rule_set in config.mandatory_rule_sets.all():
            mandatory_result = self.check_ruleset(rule_set)
            mandatory_result["name"] = str(rule_set)
            mandatory_result["id"] = rule_set.id
            mandatory_result["mandatory"] = True
            if not mandatory_result["success"]:
                results["success"] = False
            results["rule_sets"].append(mandatory_result)

            if runs_as_async_task():
                self.update_progress()

        for rule_set in config.optional_rule_sets.all():
            optional_result = self.check_ruleset(rule_set)
            optional_result["name"] = str(rule_set)
            optional_result["id"] = rule_set.id
            optional_result["mandatory"] = False
            results["rule_sets"].append(optional_result)

            if runs_as_async_task():
                self.update_progress()

        self.run.passed = results["success"]
        self.run.result = json.dumps(results)
        self.run.save()
        return self.run

    def check_ruleset(self, ruleset: RuleSet):
        """ Evaluates all rules of a ruleset for the given metadata object.

        Evaluates for each rule in a ruleset, if it evaluates to true or false.
        A ruleset will be flagged as successful, if all rules evaluated to true.

        Args:
            ruleset (RuleSet): The RuleSet to evaluate.
        Returns:
            {"success": bool, "rules": dict[]}
        """
        result = {
            "success": True,
            "rules": []
        }

        for rule in ruleset.rules.all():
            rule_result = self.check_rule(rule)

            rule_result.update(rule.as_dict())

            result["rules"].append(rule_result)
            if not rule_result["success"]:
                result["success"] = False
        return result

    def check_rule(self, rule: Rule):
        """ Evaluates a single rule for the given metadata object.

        Args:
            rule (Rule): The rule to evaluate.
        Returns:
            {"success": bool, "condition": str}: The result of the check.
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

        condition = str(real_value) + operator + str(threshold)

        return {
            "success": eval(condition, {'__builtins__': None}),
            "condition": condition
        }

    def update_progress(self):
        """Update the progress of the pending task."""
        if current_task:
            progress = AsyncResult(current_task.request.id).info.get("current", 0) + self.step_size
            # we should only set the progress to max 90
            # as the calling method might also update the progress
            progress = progress if progress <= 90 else 90
            current_task.update_state(
                state=states.STARTED,
                meta={
                    "current": progress,
                }
            )
