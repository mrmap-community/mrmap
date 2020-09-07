"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.06.19

"""
from service.helper.enums import OGCServiceEnum
from service.models import Service, Layer, FeatureType


class ServiceComparator:

    # No comparison contains attributes that are naturally different in two objects.
    # They shall not be important for checking
    no_comparison = [
        "_django_version",
        "_state",
        "created",
        "id",
        "last_modified",
        "uuid",
        "service_id"
    ]

    def __init__(self, service_a: Service, service_b: Service):
        """ Compares two services against each other and stores the differences in a dict.

        Valid combinations are only wms,wms or wfs,wfs
        Service_2 has to be the service, which is already persisted in the database.
        Service_1 has to be the service, which is not yet persisted but needs to be checked against service_2.

        Args:
            service_a (Service): The first service to be compared
            service_b (Service): The second service to be compared
        """
        if service_a.service_type.name != service_b.service_type.name:
            raise Exception("INVALID SERVICE ARGUMENTS. Service types not matching")
        self.service_a = service_a
        self.service_b = service_b

    def get_service_a(self):
        return self.service_a

    def get_service_b(self):
        return self.service_b

    def compare_services(self):
        """ The main function to be called.

        Collects all differences in metadata, layers or feature types in a diff dict.

        Returns:
             diff (dict): The differences collected
        """
        diff = {}
        if self.service_a.is_service_type(OGCServiceEnum.WMS):
            # Check layer metadata against each other
            # Always iterate over service_1 and check against service_2
            layers = [self.service_a.root_layer] + self.service_a.root_layer.get_children(all=True)
            diff["layers"] = self.compare_layers(layers)

        elif self.service_a.is_service_type(OGCServiceEnum.WFS):
            # Check feature services against each other
            # always iterate over service_1 and check against service_2
            diff["feature_types"] = self.compare_feature_types(FeatureType.objects.filter(parent_service=self.service_a))

        return diff

    def compare_layers(self, layers):
        """ Compares a list of given layers against the persisted layers in the database.

        Collects which layers must be new, which one must be updated and which one are removed

        Args:
            layers (list): The 'new' layers
        Returns:
            nothing
        """
        layers_of_b = Layer.objects.filter(parent_service=self.service_b)
        diff = {
            "new": [],
            "updated": [],
            "removed": [],
        }

        for layer_of_a in layers:
            found = False
            identifier = layer_of_a.identifier
            filtered_b_layers = layers_of_b.filter(
                identifier=identifier
            )
            count = filtered_b_layers.count()
            if count == 1:
                # Case: layer still exists and has the same identifier as before
                diff["updated"].append(layer_of_a)
            elif count == 0:
                # Case: layer from new service not found in current service -> must be a new layer!
                diff["new"].append(layer_of_a)
            else:
                # This should absolutely not happen!! Multiple identifiers found!
                raise Exception("Identifiers not unique!")

        for layer_of_b in layers_of_b:
            found = False
            for layer_of_a in layers:
                if layer_of_a.identifier == layer_of_b.identifier:
                    # case: still there
                    found = True
                    break
            if not found:
                # case: layer from old service not found in new service -> must have been removed!
                diff["removed"].append(layer_of_b)

        return diff

    def compare_feature_types(self, feature_type_list: list):
        """ Compares a list of given layers against the persisted layers in the database.

        Collects which layers must be new, which one must be updated and which one are removed

        Args:
            feature_type_list (list): The 'new' feature types as list
        Returns:
            nothing
        """
        feature_types_of_b = FeatureType.objects.filter(parent_service=self.service_b)
        diff = {
            "new": [],
            "updated": [],
            "removed": [],
        }
        for f_t_of_a in feature_type_list:

            filtered_b_f_t = feature_types_of_b.filter(metadata__identifier=f_t_of_a.metadata.identifier)

            count = filtered_b_f_t.count()
            if count == 1:
                # Case: Feature still exists and has the same identifier as before
                diff["updated"].append(f_t_of_a)
            elif count == 0:
                # Case: Feature from new service not found in current service -> must be a new Feature!
                diff["new"].append(f_t_of_a)
            else:
                # This should absolutely not happen!! Multiple identifiers found!
                raise Exception("Identifiers not unique!")

        for f_t_of_b in feature_types_of_b:
            found = False
            for f_t_of_a in feature_type_list:
                if f_t_of_a.metadata.identifier == f_t_of_b.metadata.identifier:
                    # case: still there
                    found = True
                    break
            if not found:
                # case: Feature from old service not found in new service -> must have been removed!
                diff["removed"].append(f_t_of_b)

        return diff
