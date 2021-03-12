import django_filters


class MrMapFilterSet(django_filters.FilterSet):
    def __init__(self, inline=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inline = inline