from django.forms import BaseInlineFormSet
from extra_views import InlineFormSetFactory

from registry.forms.mapcontext import MapContextLayerForm
from registry.models.mapcontext import MapContextLayer


class MapContextLayerFormSet(BaseInlineFormSet):

    # TODO instead of deleting existing layers and re-inserting new form set, perform deletes, inserts and updates
    def save(self, commit=True):
        """
        Save model instances for every form, adding and changing instances
        as necessary, and return the list of instances.
        """

        # delete all layers that existed before
        self.instance.mapcontextlayer_set.all().delete()

        new_objects = []
        for form in self.forms:
            parent_form_idx = form.cleaned_data.get("parent_form_idx", None)
            if parent_form_idx:
                parent = new_objects[int(parent_form_idx)]
                form.instance.parent = parent
            else:
                form.instance.parent = None
            model_instance = form.save(commit=False)
            # ensure there are no left-over values for MPTT-specific fields (lft, rght, tree_id, level)
            clean_model_instance = MapContextLayer(
                parent=model_instance.parent,
                map_context=model_instance.map_context,
                name=model_instance.name,
                title=model_instance.title,
                dataset_metadata=model_instance.dataset_metadata,
                layer=model_instance.layer,
                preview_image=model_instance.preview_image
            )
            clean_model_instance.save()
            new_objects.append(clean_model_instance)
            print(f"Saved {clean_model_instance}")
        return new_objects


class MapContextLayerInline(InlineFormSetFactory):
    model = MapContextLayer
    form_class = MapContextLayerForm
    prefix = 'layer'
    factory_kwargs = {'extra': 0, 'can_delete': False, 'formset': MapContextLayerFormSet}
