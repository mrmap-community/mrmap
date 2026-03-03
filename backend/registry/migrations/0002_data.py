import logging

from django.core.files.base import ContentFile
from django.db import migrations, transaction
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.ows_lib.csw.builder import CSWCapabilities
from registry.settings import MRMAP_CSW_PK


def load_initial_data(apps, schema_editor):
    MetadataContact = apps.get_model(
        "registry",
        "MetadataContact"
    )
    CatalogueService = apps.get_model(
        "registry",
        "CatalogueService"
    )
    CatalogueServiceOperationUrl = apps.get_model(
        "registry",
        "CatalogueServiceOperationUrl"
    )

    with transaction.atomic():
        contact, _ = MetadataContact.objects.get_or_create(
            **{
                "name": "MRMAP Team",
                "email": "mrmap-team@example.com",
                "phone": "+123456789",
                "postal_code": "12345",
                "city": "Example City",
                "country": "Example Country",
            }
        )

        csw, _ = CatalogueService.objects.get_or_create(
            pk=MRMAP_CSW_PK,
            defaults={
                "title": "Mr. Map CSW",
                "abstract": "CSW service for MRMAP metadata records",
                "version": OGCServiceVersionEnum.V_2_0_2.value,
                "service_contact": contact,
                "metadata_contact": contact,
            }
        )

        CatalogueServiceOperationUrl.objects.get_or_create(
            method=HttpMethodEnum.GET.value,
            operation=OGCOperationEnum.GET_CAPABILITIES.value,
            url="/csw",
            service=csw
        )
        CatalogueServiceOperationUrl.objects.get_or_create(
            method=HttpMethodEnum.GET.value,
            operation=OGCOperationEnum.GET_RECORDS.value,
            url="/csw",
            service=csw
        )
        CatalogueServiceOperationUrl.objects.get_or_create(
            method=HttpMethodEnum.POST.value,
            operation=OGCOperationEnum.GET_RECORDS.value,
            url="/csw",
            service=csw
        )
        CatalogueServiceOperationUrl.objects.get_or_create(
            method=HttpMethodEnum.GET.value,
            operation=OGCOperationEnum.GET_RECORD_BY_ID.value,
            url="/csw",
            service=csw
        )
        CatalogueServiceOperationUrl.objects.get_or_create(
            method=HttpMethodEnum.POST.value,
            operation=OGCOperationEnum.GET_RECORD_BY_ID.value,
            url="/csw",
            service=csw
        )

        capabilities = CSWCapabilities(csw)

        csw.xml_backup_file.save(
            f"{csw.pk}_capabilities.xml",
            ContentFile(capabilities.to_xml_string().encode("utf-8")),
            save=True
        )
        logging.info("MRMAP CSW service created with PK %s", MRMAP_CSW_PK)


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_initial_data),
    ]
