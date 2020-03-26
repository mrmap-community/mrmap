from model_bakery import baker

from structure.models import Group


def create_testuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.active_testuser')


def create_superadminuser():
    return baker.make_recipe('tests.baker_recipes.structure_app.superadmin_user')


def create_wms_service(group: Group):
    # ToDo: create sublayers dynamicly
    # ToDo: create x wms services
    metadata = baker.make_recipe('tests.baker_recipes.service_app.active_wms_service_metadata', created_by=group)
    return baker.make_recipe('tests.baker_recipes.service_app.active_root_wms_service', created_by=group, metadata=metadata)


def create_wfs_service(group: Group):
    # ToDo: create featuretypes dynamicly
    # ToDo: create x wfs services
    metadata = baker.make_recipe('tests.baker_recipes.service_app.active_wfs_service_metadata', created_by=group)
    return baker.make_recipe('tests.baker_recipes.service_app.active_root_wfs_service', created_by=group, metadata=metadata)
