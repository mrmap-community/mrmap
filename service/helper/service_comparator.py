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

    def __init__(self, service_1: Service, service_2: Service):
        """ Compares two services against each other and stores the differences in a dict.

        Valid combinations are only wms,wms or wfs,wfs
        Service_2 has to be the service, which is already persisted in the database.
        Service_1 has to be the service, which is not yet persisted but needs to be checked against service_2.

        Args:
            service_1 (Service): The first service to be compared
            service_2 (Service): The second service to be compared
        """
        if service_1.servicetype.name != service_2.servicetype.name:
            raise Exception("INVALID SERVICE ARGUMENTS. Service types not matching")
        self.service_1 = service_1
        self.service_2 = service_2

    def get_service_1(self):
        return self.service_1

    def get_service_2(self):
        return self.service_2

    def compare_services(self):
        """ The main function to be called.

        Collects all differences in metadata, layers or feature types in a diff dict.

        Returns:
             diff (dict): The differences collected
        """
        diff = {}
        if self.service_1.servicetype.name == OGCServiceEnum.WMS.value:
            # Check layer metadata against each other
            # Always iterate over service_1 and check against service_2
            layers = self.service_1.get_all_layers()
            diff["layers"] = self.compare_layers(layers)

        elif self.service_1.servicetype.name == OGCServiceEnum.WFS.value:
            # Check feature services against each other
            # always iterate over service_1 and check against service_2
            diff["feature_types"] = self.compare_feature_types(self.service_1.feature_type_list)

        return diff

    def compare_layers(self, layers):
        """ Compares a list of given layers against the persisted layers in the database.

        Collects which layers must be new, which one must be updated and which one are removed

        Args:
            layers (list): The 'new' layers
            diff (dict): The differences as a dict
        Returns:
            nothing
        """
        service_2_layers = Layer.objects.filter(parent_service=self.service_2)
        diff = {
            "new": [],
            "updated": [],
            "removed": [],
        }
        for layer_1 in layers:
            found = False
            for layer_2 in service_2_layers:
                if layer_1.identifier == layer_2.identifier:
                    # case: still there
                    found = True
                    diff["updated"].append(layer_1)
                    break
            if not found:
                # case: layer from new service not found in old service -> must be a new layer!
                diff["new"].append(layer_1)

        for layer_2 in service_2_layers:
            found = False
            for layer_1 in layers:
                if layer_1.identifier == layer_2.identifier:
                    # case: still there
                    found = True
                    break
            if not found:
                # case: layer from old service not found in new service -> must have been removed!
                diff["removed"].append(layer_2)

        return diff

    def compare_feature_types(self, feature_type_list: list):
        """ Compares a list of given layers against the persisted layers in the database.

        Collects which layers must be new, which one must be updated and which one are removed

        Args:
            layers (list): The 'new' layers
            diff (dict): The differences as a dict
        Returns:
            nothing
        """
        service_2_f_t = FeatureType.objects.filter(service=self.service_2)
        diff = {
            "new": [],
            "updated": [],
            "removed": [],
        }
        for f_t in feature_type_list:
            found = False
            for f_t_2 in service_2_f_t:
                if f_t.identifier == f_t_2.identifier:
                    # case: still there
                    found = True
                    diff["updated"].append(f_t)
                    break
            if not found:
                # case: layer from new service not found in old service -> must be a new layer!
                diff["new"].append(f_t)

        for f_t_2 in service_2_f_t:
            found = False
            for f_t in feature_type_list:
                if f_t.identifier == f_t_2.identifier:
                    # case: still there
                    found = True
                    break
            if not found:
                # case: layer from old service not found in new service -> must have been removed!
                diff["removed"].append(f_t_2)

        return diff
