from django.contrib.auth.models import Group
from django.contrib.gis.geos import MultiPolygon
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from model_bakery import baker, seq

from monitoring.models import MonitoringRun
from monitoring.settings import WARNING_RESPONSE_TIME
from structure.models import Organization
from users.models import MrMapUser
from service.models import OGCOperation
from service.helper.enums import MetadataEnum, OGCOperationEnum, ResourceOriginEnum, MetadataRelationEnum
from service.models import Service, Metadata
from tests.utils import generate_random_string



def create_testuser(groups=None):
    # Check if testuser already exists
    try:
        testuser = MrMapUser.objects.get(
            username="Testuser",
            email="test@example.com"
        )
        return testuser
    except ObjectDoesNotExist:
        pass

    if groups is not None:
        return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser',
                                 groups=groups)
    else:
        return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser(groups=None):
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

    return superuser


def create_wms_service(group: Organization,
                       is_update_candidate_for: Service = None,
                       user: MrMapUser = None,
                       contact: Organization = None,
                       how_much_services: int = 1,
                       how_much_sublayers: int = 1,
                       md_relation_origin: str = None):
    service_md_type = MetadataEnum.SERVICE.value

    layer_md_type = MetadataEnum.LAYER.value

    dataset_md_type = MetadataEnum.DATASET.value

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wms_service_metadata',
        _quantity=how_much_services,
        metadata_type=service_md_type,
        contact=contact,
    )

    for root_service_metadata in root_service_metadatas:

        dataset_metadata = baker.make_recipe(
            'tests.baker_recipes.service_app.active_dataset_metadata',
            metadata_type=dataset_md_type,
            contact=contact,
        )

        baker.make_recipe(
            'tests.baker_recipes.service_app.active_dataset',
            metadata=dataset_metadata,
        )

        obj = baker.make_recipe(
            'tests.baker_recipes.service_app.metadata_document',
            metadata=dataset_metadata,
        )

        if md_relation_origin:
            md_origin = md_relation_origin
        else:
            md_origin = ResourceOriginEnum.CAPABILITIES.value

        root_service_metadata.add_metadata_relation(to_metadata=dataset_metadata,
                                                    origin=md_origin,
                                                    relation_type=MetadataRelationEnum.DESCRIBES.value)

        baker.make_recipe(
            'tests.baker_recipes.service_app.capability_document',
            metadata=root_service_metadata,
        )

        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wms_service',
            metadata=root_service_metadata,
            is_update_candidate_for=is_update_candidate_for,
        )

        root_layer_metadata = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
            contact=contact,
        )

        root_layer = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_sublayer',
            parent_service=root_service,
            metadata=root_layer_metadata[0],
            identifier=root_layer_metadata[0].identifier,
        )

        root_service.root_layer = root_layer
        root_service.save()

        sublayer_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wms_layer_metadata',
            _quantity=how_much_sublayers,
            metadata_type=layer_md_type,
            contact=contact,

        )

        for sublayer_metadata in sublayer_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wms_sublayer',
                parent_service=root_service,
                metadata=sublayer_metadata,
                parent=root_layer,
                identifier=sublayer_metadata.identifier,
            )

    return root_service_metadatas


def create_wfs_service(group: Organization,
                       is_update_candidate_for: Service = None,
                       user: MrMapUser = None,
                       contact: Organization = None,
                       how_much_services: int = 1,
                       how_much_featuretypes: int = 1,
                       md_relation_origin: str = None):

    service_md_type = MetadataEnum.SERVICE.value

    feature_type_md_type = MetadataEnum.FEATURETYPE.value

    dataset_md_type = MetadataEnum.DATASET.value

    root_service_metadatas = baker.make_recipe(
        'tests.baker_recipes.service_app.active_wfs_service_metadata',
        _quantity=how_much_services,
        metadata_type=service_md_type,
        contact=contact,
    )

    for root_service_metadata in root_service_metadatas:
        dataset_metadata = baker.make_recipe(
            'tests.baker_recipes.service_app.active_dataset_metadata',
            metadata_type=dataset_md_type,
            contact=contact,
        )

        baker.make_recipe(
            'tests.baker_recipes.service_app.active_dataset',
            metadata=dataset_metadata,
        )

        baker.make_recipe(
            'tests.baker_recipes.service_app.metadata_document',
            metadata=dataset_metadata,
        )

        if md_relation_origin:
            md_origin = md_relation_origin
        else:
            md_origin = ResourceOriginEnum.CAPABILITIES.value

        root_service_metadata.add_metadata_relation(to_metadata=dataset_metadata,
                                                    relation_type=MetadataRelationEnum.DESCRIBES.value,
                                                    origin=md_origin)

        baker.make_recipe(
            'tests.baker_recipes.service_app.capability_document',
            metadata=root_service_metadata,
        )

        root_service = baker.make_recipe(
            'tests.baker_recipes.service_app.active_root_wfs_service',
            metadata=root_service_metadata,
            is_update_candidate_for=is_update_candidate_for,
        )

        featuretype_metadatas = baker.make_recipe(
            'tests.baker_recipes.service_app.active_wfs_featuretype_metadata',
            _quantity=how_much_featuretypes,
            metadata_type=feature_type_md_type,
            contact=contact,
        )

        for featuretype_metadata in featuretype_metadatas:
            baker.make_recipe(
                'tests.baker_recipes.service_app.active_wfs_featuretype',
                parent_service=root_service,
                metadata=featuretype_metadata,
            )

    return root_service_metadatas


def create_non_autogenerated_orgas(user: MrMapUser, how_much_orgas: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.non_autogenerated_orga',
                             _quantity=how_much_orgas)


def create_random_named_orgas(user: MrMapUser, how_much_orgas: int = 1):
    orga_list = []

    for i in range(0, how_much_orgas):
        orga_list += baker.make_recipe(
            'tests.baker_recipes.structure_app.non_autogenerated_orga',
            _quantity=1,
            name=generate_random_string(5)
        )

    return orga_list


def create_public_organization():
    return baker.make_recipe(
        'tests.baker_recipes.structure_app.non_autogenerated_orga',
        _quantity=1,
        name="Publicity"
    )


def create_publish_request(group: Organization, orga: Organization,
                           message: str = "Test"):
    return baker.make_recipe('tests.baker_recipes.structure_app.publish_request',
                             group=group,
                             organization=orga,
                             message=message)


def create_pending_task(group: Organization, how_much_pending_tasks: int = 1):
    return baker.make_recipe('tests.baker_recipes.structure_app.pending_task',
                             task_id=seq(1),
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


def create_operation(operation_name: OGCOperationEnum):
    return baker.make_recipe(
        "tests.baker_recipes.service_app.operation",
        operation_name=operation_name
    )


def create_proxy_logs(user, num: int = 1):
    return baker.make_recipe(
        "tests.baker_recipes.service_app.proxy_log",
        _quantity=num,
        user=user,
    )


def create_monitoring_run(end=timezone.now(), how_much_runs: int = 1,):
    return baker.make_recipe(
        "tests.baker_recipes.monitoring_app.monitoring_run",
        end=end,
        _quantity=how_much_runs,
    )


def create_monitoring_result(metadata: Metadata,
                             monitoring_run: MonitoringRun,
                             duration=timezone.timedelta(milliseconds=WARNING_RESPONSE_TIME-1),
                             status_code: int = 200,
                             available: bool = True,
                             timestamp=None):

    if not monitoring_run:
        monitoring_run = create_monitoring_run()

    if timestamp:
        return baker.make_recipe(
            "tests.baker_recipes.monitoring_app.monitoring_result",
            metadata=metadata,
            duration=duration,
            status_code=status_code,
            available=available,
            monitoring_run=monitoring_run,
            timestamp=timestamp,
        )
    else:
        return baker.make_recipe(
            "tests.baker_recipes.monitoring_app.monitoring_result",
            metadata=metadata,
            duration=duration,
            status_code=status_code,
            available=available,
            monitoring_run=monitoring_run,
        )


def create_ogc_operations(operations: list):
    ogc_operations = []
    for operation in operations:
        ogc_operations.append(
            baker.make_recipe(
                "tests.baker_recipes.service_app.ogc_operation",
                operation=operation
            )
        )
    return ogc_operations


def create_allowed_operation(allowed_groups: QuerySet(Group),
                             operations: QuerySet(OGCOperation),
                             root_metadata: Metadata,
                             how_much_allowed_operations: int = 1,
                             allowed_area: MultiPolygon = None,):

    return baker.make_recipe(
        "tests.baker_recipes.service_app.allowed_operation",
        _quantity=how_much_allowed_operations,
        root_metadata=root_metadata,
        allowed_groups=allowed_groups,
        operations=operations,
        allowed_area=allowed_area,
    )
