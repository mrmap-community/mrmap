# Generated by Django 3.1.8 on 2021-06-07 14:07

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('acl', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('service', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='metadatauserobjectpermission',
            name='content_object',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.metadata'),
        ),
        migrations.AddField(
            model_name='metadatauserobjectpermission',
            name='permission',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='auth.permission'),
        ),
    ]