from enum import Enum


class EnumChoice(Enum):
    """Provides basic functionality for Enums"""

    @classmethod
    def as_choices(cls, drop_empty_choice: bool = False):
        empty_choice = [] if drop_empty_choice else [(None, "---")]
        choices = empty_choice + [(enum.value, enum.value) for enum in cls]
        return choices
