from rest_framework_json_api.relations import HyperlinkedRelatedField


class ExtendedHyperlinkedRelatedField(HyperlinkedRelatedField):
    """extend the rest_framework_json_api.relations.HyperlinkedRelatedField by adding
    the possibility to add meta key on json:api response per related field
    """

    def __init__(self, self_link_view_name=None, related_link_view_name=None, meta_attrs=None, **kwargs):
        super().__init__(self_link_view_name=self_link_view_name,
                         related_link_view_name=related_link_view_name, **kwargs)
        self.meta_attrs = meta_attrs

    def get_links(self, obj=None, lookup_field="pk"):
        links = super().get_links(obj=obj, lookup_field=lookup_field)
        # FIXME: make it save to execute on runtime if AttributeError occours
        if self.meta_attrs:
            meta = {}
            for lookup, name in self.meta_attrs.items():
                try:
                    meta.update({name: getattr(obj, lookup)})
                except AttributeError:
                    # TODO: print warning that the attribute is not present
                    pass
            if meta:
                links.update({'meta': meta})
        return links
