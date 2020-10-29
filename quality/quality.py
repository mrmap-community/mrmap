"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from typing import Union

from quality.enums import RulePropertyEnum
from quality.models import ConformityCheckConfigurationInternal, \
    ConformityCheckConfigurationExternal, Rule, ConformityCheckRun
from service.models import Metadata


class Quality:

    def run_check(self, metadata: Metadata,
                  config: Union[ConformityCheckConfigurationInternal, ConformityCheckConfigurationExternal]):
        if metadata is None:
            raise Exception("Could not check conformity. Metadata is None.")

        if config is None:
            raise Exception("Could not check conformity. ConformityCheckConfiguration is None.")

        run = ConformityCheckRun.objects.create(
            metadata=metadata, conformity_check_configuration=config)

        if isinstance(config, ConformityCheckConfigurationInternal):
            self.check_internal(run)
        elif isinstance(config, ConformityCheckConfigurationExternal):
            self.check_external(run)
        else:
            raise Exception("Could not check conformity. Invalid configuration.")


    # def run_check(self, run: ConformityCheckRun) -> None:
    #     # TODO What to do with result
    #     config = run.conformity_check_configuration
    #     if config.is_internal():
    #         self.check_internal(run)
    #
    #     elif config.is_external():
    #         self.check_external(run)
    #
    #     else:
    #         raise Exception("Could not check conformity. Invalid configuration.")

    def check_internal(self, run: ConformityCheckRun):
        config = run.conformity_check_configuration
        metadata = run.metadata

        mandatory_results = []
        for rule_set in config.mandatory_rule_sets.all():
            for rule in rule_set.rules.all():
                # TODO handle response
                self.check_rule(rule, metadata)

        optional_results = []
        for rule_set in config.optional_rule_sets.all():
            for rule in rule_set.rules.all():
                # TODO handle response
                self.check_rule(rule, metadata)

    def check_external(self, configuration: ConformityCheckConfigurationExternal):
        pass

    def check_rule(self, rule: Rule, metadata: Metadata):
        prop = rule.property
        operator = rule.operator
        field = rule.field_name
        value = rule.value
        real_value = None

        if prop == RulePropertyEnum.LEN.value:
            if not self.property_allowed_for_field(prop, field):
                raise Exception(f"Property {prop} is not allowed for field {field}")

            attribute = metadata.__getattribute__(field)
            real_value = len(attribute)

        elif prop == RulePropertyEnum.COUNT.value:
            if not self.property_allowed_for_field(prop, field):
                raise Exception(f"Property {prop} is not allowed for field {field}")

            manager = metadata.__getattribute__(field)
            elements = manager.all()
            real_value = elements.count()

        # TODO Do we really want to cast value to String?
        #      Do we have to cast to different types?
        condition = str(real_value) + operator + str(value)
        return eval(condition, {'__builtins__': None})

    def property_allowed_for_field(self, prop, field) -> bool:
        # TODO check if the property is allowed for the field
        pass
