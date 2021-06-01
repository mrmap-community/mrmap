import django_tables2 as tables
from main.tables.template_code import RECORD_ABSOLUTE_LINK_VALUE_CONTENT
from resourceNew.models import DatasetMetadata
from guardian.core import ObjectPermissionChecker
from django.utils.html import format_html


class DatasetMetadataTable(tables.Table):
    perm_checker = None
    title = tables.TemplateColumn(template_code=RECORD_ABSOLUTE_LINK_VALUE_CONTENT)
    related_objects = tables.Column(empty_values=[])

    # todo
    """actions = tables.TemplateColumn(verbose_name=_('Actions'),
                                    empty_values=[],
                                    orderable=False,
                                    template_code=RESOURCE_TABLE_ACTIONS,
                                    attrs={"td": {"style": "white-space:nowrap;"}},
                                    extra_context={'perm_checker': perm_checker})"""

    class Meta:
        model = DatasetMetadata
        fields = ('title',)
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'dataset-metadata-table'

    def before_render(self, request):
        self.perm_checker = ObjectPermissionChecker(request.user)
        # if we call self.data, all object from the underlying queryset will be selected. But in case of paging, only a
        # subset of the self.data is needed. django tables2 doesn't provide any way to get the cached qs of the current
        # page. So the following code snippet is a workaround to collect the current presented objects of the table
        # to avoid calling the database again.
        objs = []
        for obj in self.page.object_list:
            objs.append(obj.record)
        # for all objects of the current page, we prefetch all permissions for the given user. This optimizes the
        # rendering of the action column, cause we need to check if the user has the permission to perform the given
        # action. If we don't prefetch the permissions, any permission check in the template will perform one db query
        # for each object.
        if objs:
            self.perm_checker.prefetch_perms(objs)

    def render_related_objects(self, record):
        links = ""
        for layer in record.self_pointing_layers.all():
            links += f'<a href="{layer.get_absolute_url()}">{layer.icon} {layer}</a>, '
        for feature_type in record.self_pointing_feature_types.all():
            links += f'<a href="{feature_type.get_absolute_url()}">{feature_type.icon} {feature_type}</a>, '

        return format_html(links)
