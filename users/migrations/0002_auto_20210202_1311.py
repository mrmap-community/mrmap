# Generated by Django 3.1.5 on 2021-02-02 12:11

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('service', '0011_auto_20210128_1054'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='metadata',
            field=models.ForeignKey(help_text='Select the service you want to subscribe. When you edit an existing subscription, you can not change this selection.', on_delete=django.db.models.deletion.CASCADE, to='service.metadata', verbose_name='Service'),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='notify_on_access_edit',
            field=models.BooleanField(default=True, help_text="Sends an e-mai if the service's access has been changed.", verbose_name='Notify on access edit'),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='notify_on_metadata_edit',
            field=models.BooleanField(default=True, help_text="Sends an e-mai if the service's metadata has been changed.", verbose_name='Notify on metadata edit'),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='notify_on_update',
            field=models.BooleanField(default=True, help_text='Sends an e-mai if the service has been updated.', verbose_name='Notify on update'),
        ),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together={('metadata', 'user')},
        ),
    ]
