# Generated by Django 3.2.7 on 2021-09-21 13:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resourceNew', '0003_auto_20210917_1002'),
    ]

    operations = [
        migrations.AddField(
            model_name='mapcontextlayer',
            name='dataset_metadata',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='resourceNew.datasetmetadata'),
        ),
    ]
