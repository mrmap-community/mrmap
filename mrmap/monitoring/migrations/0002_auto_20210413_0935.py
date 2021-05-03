# Generated by Django 3.1.8 on 2021-04-13 07:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
        ('service', '0001_initial'),
        ('monitoring', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='monitoringsetting',
            name='metadatas',
            field=models.ManyToManyField(related_name='monitoring_setting', to='service.Metadata'),
        ),
        migrations.AddField(
            model_name='monitoringsetting',
            name='periodic_task',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='django_celery_beat.periodictask'),
        ),
        migrations.AddField(
            model_name='monitoringrun',
            name='metadatas',
            field=models.ManyToManyField(related_name='monitoring_runs', to='service.Metadata', verbose_name='Checked resources'),
        ),
        migrations.AddField(
            model_name='monitoringresult',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.metadata', verbose_name='Resource'),
        ),
        migrations.AddField(
            model_name='monitoringresult',
            name='monitoring_run',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='monitoring_results', to='monitoring.monitoringrun'),
        ),
        migrations.AddField(
            model_name='healthstatereason',
            name='health_state',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reasons', to='monitoring.healthstate'),
        ),
        migrations.AddField(
            model_name='healthstatereason',
            name='monitoring_result',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='health_state_reasons', to='monitoring.monitoringresult'),
        ),
        migrations.AddField(
            model_name='healthstate',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='health_state', to='service.metadata', verbose_name='Resource'),
        ),
        migrations.AddField(
            model_name='healthstate',
            name='monitoring_run',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='health_state', to='monitoring.monitoringrun', verbose_name='Monitoring Run'),
        ),
    ]