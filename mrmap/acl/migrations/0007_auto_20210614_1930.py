# Generated by Django 3.2.3 on 2021-06-14 17:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('acl', '0006_auto_20210614_1014'),
    ]

    operations = [
        migrations.AlterField(
            model_name='metadatagroupobjectpermission',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='metadatauserobjectpermission',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
    ]
