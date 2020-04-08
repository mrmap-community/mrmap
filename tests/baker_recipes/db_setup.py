from model_bakery import baker

from service.helper.enums import MetadataEnum
from service.models import MetadataType
from structure.models import MrMapGroup


def create_testuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser():
    superuser = baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user')
    public_group = baker.make_recipe('tests.baker_recipes.structure_app.public_group', created_by=superuser)
    public_group.user_set.add(superuser)
    return superuser


def create_wms_service(group: MrMapGroup, how_much_services: int = 1, how_much_sublayers: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    layer_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.LAYER.value
    )[0]

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wms_service_metadata',
        created_by=group,
        _quantity=how_much_services,
        metadata_type=service_md_type,
    )

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wms_service',
            created_by=group,
            metadata=root_service_metadata
        )

        sublayer_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            created_by=group,
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
        )

        for sublayer_metadata in sublayer_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wms_sublayer',
                created_by=group,
                parent_service=root_service,
                metadata=sublayer_metadata,
            )

    return root_service_metadatas


def create_wfs_service(group: MrMapGroup, how_much_services: int = 1, how_much_featuretypes: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    feature_type_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.FEATURETYPE.value
    )[0]

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wfs_service_metadata',
        created_by=group,
        _quantity=how_much_services,
        metadata_type=service_md_type,
    )

    for root_service_metadata in root_service_metadatas:
        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wfs_service',
            created_by=group,
            metadata=root_service_metadata,
        )

        featuretype_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wfs_featuretype_metadata',
            created_by=group,
            _quantity=how_much_featuretypes,
            metadata_type=feature_type_md_type,
        )

        for featuretype_metadata in featuretype_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wfs_featuretype',
                created_by=group,
                parent_service=root_service,
                metadata=featuretype_metadata
            )

    return root_service_metadatas
