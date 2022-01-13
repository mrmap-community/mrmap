# Generated by Django 3.2.9 on 2022-01-07 11:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0003_auto_20220107_1043'),
    ]

    operations = [
        migrations.AddField(
            model_name='mapcontextlayer',
            name='is_leaf',
            field=models.BooleanField(default=False, help_text='Set if this map context layer is a layer withattributes (leaf) or it defines a group of layers like a folder (not leaf).', verbose_name='Is tree leaf'),
        ),
    ]
