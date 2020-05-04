

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from model_bakery import baker, seq
from structure.models import MrMapUser, Organization
from service.helper.enums import MetadataEnum
from service.models import MetadataType, Service, Document
from structure.models import MrMapGroup
from tests.utils import generate_random_string


def create_testuser():
    # Check if testuser already exists
    try:
        testuser = MrMapUser.objects.get(
            username="Testuser",
            email="test@example.com"
        )
        return testuser
    except ObjectDoesNotExist:
        pass
    return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser(groups: QuerySet = None,):
    # Check if superadminuser already exists
    try:
        superuser = MrMapUser.objects.get(
            username="Superuser",
            email="test@example.com"
        )
        return superuser
    except ObjectDoesNotExist:
        pass

    if groups is not None:
        superuser = baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user',
                                      groups=groups)
    else:
        superuser = baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user')

    public_group = baker.make_recipe('tests.baker_recipes.structure_app.public_group', created_by=superuser)
    public_group.user_set.add(superuser)
    return superuser


def create_wms_service(group: MrMapGroup, is_update_candidate_for: Service=None, user: MrMapUser=None, contact: Organization=None, how_much_services: int = 1, how_much_sublayers: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    layer_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.LAYER.value
    )[0]

    if is_update_candidate_for is not None and user is not None:
        root_service_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_service_metadata',
            created_by=group,
            _quantity=how_much_services,
            metadata_type=service_md_type,
            is_update_candidate_for=is_update_candidate_for.metadata,
            created_by_user=user,
            contact=contact,
        )
    else:
        root_service_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_service_metadata',
            created_by=group,
            _quantity=how_much_services,
            metadata_type=service_md_type,
            contact=contact,
        )

    for root_service_metadata in root_service_metadatas:

        baker.make_recipe(
            'tests.baker_recipes.service_app.document',
            related_metadata=root_service_metadata,
            is_update_candidate_for=Document.objects.get(related_metadata=is_update_candidate_for.metadata) if is_update_candidate_for is not None else None,
            created_by_user=user if user is not None else None,
        )

        if is_update_candidate_for is not None and user is not None:
            root_service = baker.make_recipe(
                'tests.baker_recipes.service_app.active_root_wms_service',
                created_by=group,
                metadata=root_service_metadata,
                is_update_candidate_for=is_update_candidate_for,
                created_by_user=user,
            )
        else:
            root_service = baker.make_recipe(
                'tests.baker_recipes.service_app.active_root_wms_service',
                created_by=group,
                metadata=root_service_metadata,
            )

        root_layer_metadata = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            created_by=group,
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
            contact=contact,
        )

        root_layer = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_sublayer',
            created_by=group,
            parent_service=root_service,
            metadata=root_layer_metadata[0],
            identifier=root_layer_metadata[0].identifier,
        )

        root_service.root_layer = root_layer
        root_service.save()

        sublayer_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            created_by=group,
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
            contact=contact,
        )

        for sublayer_metadata in sublayer_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wms_sublayer',
                created_by=group,
                parent_service=root_service,
                metadata=sublayer_metadata,
                parent_layer=root_layer,
                identifier=sublayer_metadata.identifier

            )

    return root_service_metadatas


def create_wfs_service(group: MrMapGroup, is_update_candidate_for: Service = None, user: MrMapUser = None, contact: Organization=None, how_much_services: int = 1, how_much_featuretypes: int = 1):
    service_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.SERVICE.value
    )[0]

    feature_type_md_type = MetadataType.objects.get_or_create(
        type=MetadataEnum.FEATURETYPE.value
    )[0]

    if is_update_candidate_for is not None and user is not None:
        root_service_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wfs_service_metadata',
            created_by=group,
            _quantity=how_much_services,
            metadata_type=service_md_type,
            is_update_candidate_for=is_update_candidate_for.metadata,
            created_by_user=user,
            contact=contact,
        )
    else:
        root_service_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wfs_service_metadata',
            created_by=group,
            _quantity=how_much_services,
            metadata_type=service_md_type,
            contact=contact,
        )

    for root_service_metadata in root_service_metadatas:
        baker.make_recipe(
            'tests.baker_recipes.service_app.document',
            related_metadata=root_service_metadata,
            is_update_candidate_for=Document.objects.get(related_metadata=is_update_candidate_for.metadata) if is_update_candidate_for is not None else None,
            created_by_user=user if user is not None else None,
        )

        if is_update_candidate_for is not None and user is not None:
            root_service = baker.make_recipe(
                'tests.baker_recipes.service_app.active_root_wfs_service',
                created_by=group,
                metadata=root_service_metadata,
                is_update_candidate_for=is_update_candidate_for,
                created_by_user=user,
            )
        else:
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
            contact=contact,
        )

        for featuretype_metadata in featuretype_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wfs_featuretype',
                created_by=group,
                parent_service=root_service,
                metadata=featuretype_metadata,
            )

    return root_service_metadatas


def create_guest_groups(user: MrMapUser = None, how_much_groups: int = 1):

    # Check for already existing groups to fetch the next sequence integer
    existing_groups = MrMapGroup.objects.filter(
        name__icontains="GuestGroup"
    ).order_by("-name")

    if existing_groups.count() > 0:
        # Get last incremented sequence id from name
        first = existing_groups.first()
        first_num = int(first.name.replace("GuestGroup", ""))
    else:
        first_num = -1

    if user is not None:
        groups = baker.make_recipe(
            'tests.baker_recipes.structure_app.guest_group',
            created_by=user,
            _quantity=how_much_groups,
            name=seq("GuestGroup", increment_by=1, start=first_num + 1)
        )
    else:
        groups = baker.make_recipe(
            'tests.baker_recipes.structure_app.guest_group',
            _quantity=how_much_groups,
            name=seq("GuestGroup", increment_by=1, start=first_num + 1)
        )

    return groups


def create_non_autogenerated_orgas(user: MrMapUser, how_much_orgas: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.non_autogenerated_orga',
                             created_by=user,
                             _quantity=how_much_orgas)


def create_random_named_orgas(user: MrMapUser, how_much_orgas: int = 1):
    orga_list = []

    for i in range(0, how_much_orgas):
        orga_list += baker.make_recipe(
            'tests.baker_recipes.structure_app.non_autogenerated_orga',
            created_by=user,
            _quantity=1,
            organization_name=generate_random_string(5)
        )

    return orga_list


def create_public_organization(user: MrMapUser):
    return baker.make_recipe(
        'tests.baker_recipes.structure_app.non_autogenerated_orga',
        created_by=user,
        _quantity=1,
        organization_name="Publicity"
    )


def create_pending_request(group: MrMapGroup = None, orga: Organization = None, type_str: str = None, how_much_requests: int = 1):

    if group is not None and type_str is not None and orga is not None:
        return baker.make_recipe('tests.baker_recipes.structure_app.pending_request',
                                 group=group,
                                 type=type_str,
                                 organization=orga,
                                 _quantity=how_much_requests)
    else:
        return baker.make_recipe('tests.baker_recipes.structure_app.pending_request',
                                 _quantity=how_much_requests)


def create_pending_task(group: MrMapGroup, how_much_pending_tasks: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.pending_task',
                             created_by=group,
                             _quantity=how_much_pending_tasks)


def create_keywords(num: int = 1):
    return baker.make_recipe(
        "tests.baker_recipes.service_app.keyword",
        _quantity=num
    )


def create_categories(num: int = 1):
    return baker.make_recipe(
        "tests.baker_recipes.service_app.category",
        _quantity=num
    )
