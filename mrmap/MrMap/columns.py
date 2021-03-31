import django_tables2 as tables


class MrMapColumn(tables.Column):
    def __init__(self, tooltip=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tooltip = tooltip
