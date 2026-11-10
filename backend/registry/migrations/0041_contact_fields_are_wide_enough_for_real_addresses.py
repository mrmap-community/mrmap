"""The contact fields of a metadata contact are as wide as real addresses.

The contact block of a Capabilities or ISO record is free text: the address of
the WMS "ZDM der GDWS Standort Kiel" carries well over 100 characters and the
INSERT the persistence handler runs for it -- one ``bulk_create`` with
``ignore_conflicts``, which by design never asks the model for validation --
reached Postgres with ``varchar(100)`` columns and answered
``value too long for type character varying(100)`` without naming the field;
the whole registration transaction rolled back and the service could not be
registered at all (#1211).

Therefore the nine fields which were capped at 100 -- email, phone, facsimile,
city, postal_code, address_type, address, state_or_province and country --
carry 255 now, the width the issue proposes and what the other free-text
fields of this model (``name`` with 256) already answer. A widening
``ALTER TABLE ... TYPE varchar(255)`` rewrites no rows and no index on
Postgres; the way back narrows the columns again and refuses deployment while
a stored value is over 100, which is what a narrowing has always done.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0040_catalogueservicegetcapabilitiesproberesult_error_detail_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='metadatacontact',
            name='address',
            field=models.CharField(default='', max_length=255, verbose_name='Address'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='address_type',
            field=models.CharField(default='', max_length=255, verbose_name='Address type'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='city',
            field=models.CharField(default='', max_length=255, verbose_name='City'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='country',
            field=models.CharField(default='', max_length=255, verbose_name='Country'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='email',
            field=models.EmailField(default='', max_length=255, verbose_name='E-Mail'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='facsimile',
            field=models.CharField(default='', max_length=255, verbose_name='Facsimile'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='phone',
            field=models.CharField(default='', max_length=255, verbose_name='Phone'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='postal_code',
            field=models.CharField(default='', max_length=255, verbose_name='Postal code'),
        ),
        migrations.AlterField(
            model_name='metadatacontact',
            name='state_or_province',
            field=models.CharField(default='', max_length=255, verbose_name='State or province'),
        ),
    ]
