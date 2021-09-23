# Generated by Django 3.2.7 on 2021-09-23 13:27

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('name', models.CharField(help_text='Describe what this jobs does.', max_length=256, verbose_name='name')),
                ('created_by_user', models.ForeignKey(blank=True, editable=False, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_job_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('last_modified_by', models.ForeignKey(blank=True, editable=False, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_job_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by')),
                ('owned_by_org', models.ForeignKey(blank=True, editable=False, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_job_owned_by_org', to='users.organization', verbose_name='Owner')),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('status', models.CharField(choices=[(None, '---'), ('pending', 'pending'), ('started', 'started'), ('success', 'success'), ('failure', 'failure')], default='pending', help_text='Current state of the task being run', max_length=50, verbose_name='task state')),
                ('name', models.CharField(help_text='Describe what this jobs does.', max_length=256, verbose_name='name')),
                ('phase', models.TextField(default='')),
                ('progress', models.FloatField(default=0.0)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('done_at', models.DateTimeField(blank=True, null=True)),
                ('traceback', models.TextField(blank=True, null=True)),
                ('created_by_user', models.ForeignKey(blank=True, editable=False, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_task_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('job', models.ForeignKey(help_text='the parent task of this sub task', on_delete=django.db.models.deletion.CASCADE, related_name='tasks', related_query_name='task', to='jobs.job', verbose_name='parent task')),
                ('last_modified_by', models.ForeignKey(blank=True, editable=False, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_task_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by')),
                ('owned_by_org', models.ForeignKey(blank=True, editable=False, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs_task_owned_by_org', to='users.organization', verbose_name='Owner')),
            ],
            options={
                'ordering': ['-done_at'],
            },
        ),
    ]
