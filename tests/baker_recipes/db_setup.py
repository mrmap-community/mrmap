from model_bakery import baker

from structure.models import MrMapGroup


def create_testuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user')


def create_wms_service(group: MrMapGroup, how_much_services: int = 1, how_much_sublayers: int = 1):
    root_service_metadatas = baker.make_recipe('tests.baker_recipes.service_app.active_wms_service_metadata',
                                               created_by=group,
                                               _quantity=how_much_services)

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe('tests.baker_recipes.service_app.active_root_wms_service',
                                         created_by=group,
                                         metadata=root_service_metadata)

        sublayer_metadatas = baker.make_recipe('tests.baker_recipes.service_app.active_wms_layer_metadata',
                                               created_by=group,
                                               _quantity=how_much_sublayers)

        for sublayer_metadata in sublayer_metadatas:
            baker.make_recipe('tests.baker_recipes.service_app.active_wms_sublayer',
                              created_by=group,
                              parent_service=root_service,
                              metadata=sublayer_metadata)

    return root_service_metadatas


def create_wfs_service(group: MrMapGroup, how_much_services: int = 1, how_much_featuretypes: int = 1):
    root_service_metadatas = baker.make_recipe('tests.baker_recipes.service_app.active_wfs_service_metadata',
                                               created_by=group,
                                               _quantity=how_much_services)

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe('tests.baker_recipes.service_app.active_root_wfs_service',
                                         created_by=group,
                                         metadata=root_service_metadata)

        featuretype_metadatas = baker.make_recipe('tests.baker_recipes.service_app.active_wfs_featuretype_metadata',
                                                  created_by=group,
                                                  _quantity=how_much_featuretypes)

        for featuretype_metadata in featuretype_metadatas:
            baker.make_recipe('tests.baker_recipes.service_app.active_wfs_featuretype',
                              created_by=group,
                              parent_service=root_service,
                              metadata=featuretype_metadata)

    return root_service_metadatas
