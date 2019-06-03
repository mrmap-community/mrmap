"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 03.06.19

"""
from service.models import Service, Metadata, Layer


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
        self._load_relational_fields_to_lists(service_2.metadata)

    def get_service_1(self):
        return self.service_1

    def get_service_2(self):
        return self.service_2

    def _load_relational_fields_to_lists(self, metadata):
        """ Since Many-To-Many fields can not be compared against temporary list structures (which are normally provided by service_1),
        we need to load those relational fields into the corresponding list objects.

        Returns:
             nothing
        """
        # keywords
        for kw in metadata.keywords.all():
            metadata.keywords_list.append(kw)

        # reference systems
        for srs in metadata.reference_system.all():
            metadata.reference_system_list.append(srs)

    def compare_services(self):
        diff = {}

        # Check service metadata against each other
        diff_services = {}
        md_1 = self.service_1.metadata
        md_2 = self.service_2.metadata
        self.compare_metadata(md_1, md_2, diff_services)

        # Check layer metadata against each other
        # Always iterate over service_1 and check against service_2
        diff_layers = {}
        self.compare_layer([self.service_1.root_layer], diff_layers)
        diff["layers"] = diff_layers
        diff["services"] = diff_services
        return diff

    def compare_layer(self, layers, diff: dict):
        for layer_1 in layers:
            # get layer identifier and check if this exists in the other service
            layer_2 = Layer.objects.filter(identifier=layer_1.identifier, parent_service=self.service_2)
            if layer_2.count() == 0:
                # no such layer existing in other service
                diff[layer_1.identifier] = {
                    "md_1": layer_1,
                    "md_2": None
                }
            elif layer_2.count() > 1:
                raise Exception("MULTIPLE LAYERS FOR SAME IDENTIFIER FOUND: " + layer_1.identifier)
            else:
                layer_2 = layer_2[0]
                self._load_relational_fields_to_lists(layer_2.metadata)
                self.compare_metadata(layer_1.metadata, layer_2.metadata, diff)
            if len(layer_1.children_list) > 0:
                self.compare_layer(layer_1.children_list, diff)


    def compare_metadata(self, metadata_1: Metadata, metadata_2: Metadata, diff:dict):
        metadata_2_dict = metadata_2.__dict__
        for md_key, md_val_1 in metadata_1.__dict__.items():
            if md_key in self.no_comparison:
                continue

            md_val_2 = metadata_2_dict.get(md_key)
            if isinstance(md_val_1, list):
                for val in md_val_1:
                    if val not in md_val_2:
                        diff[md_key] = {
                            "md_1": md_val_1,
                            "md_2": md_val_2,
                        }
                        break
            else:
                if md_val_1 != md_val_2:
                    diff[md_key] = {
                        "md_1": md_val_1,
                        "md_2": md_val_2
                    }
        return diff
