# Generated by Django 3.1.8 on 2021-05-04 07:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('quality', '0001_initial'),
        ('service', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conformitycheckrun',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.metadata'),
        ),
        migrations.AddField(
            model_name='conformitycheckconfigurationinternal',
            name='mandatory_rule_sets',
            field=models.ManyToManyField(related_name='mandatory_rule_sets', to='quality.RuleSet'),
        ),
        migrations.AddField(
            model_name='conformitycheckconfigurationinternal',
            name='optional_rule_sets',
            field=models.ManyToManyField(blank=True, related_name='optional_rule_sets', to='quality.RuleSet'),
        ),
    ]
