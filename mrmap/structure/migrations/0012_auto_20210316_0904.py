# Generated by Django 3.1.7 on 2021-03-16 08:04

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('structure', '0011_auto_20210315_1615'),
    ]

    operations = [
        migrations.AlterField(
            model_name='errorreport',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.group'),
        ),
        migrations.AlterField(
            model_name='groupactivity',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='auth.group'),
        ),
        migrations.AlterField(
            model_name='groupinvitationrequest',
            name='activation_until',
            field=models.DateTimeField(default=datetime.datetime(2021, 4, 15, 8, 4, 21, 896110, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='groupinvitationrequest',
            name='created_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.group'),
        ),
        migrations.AlterField(
            model_name='groupinvitationrequest',
            name='group',
            field=models.ForeignKey(help_text='Invite the selected user to this group.', on_delete=django.db.models.deletion.CASCADE, related_name='pending_group_invitations', to='structure.mrmapgroup', verbose_name='to group'),
        ),
        migrations.AlterField(
            model_name='groupinvitationrequest',
            name='user',
            field=models.ForeignKey(help_text='Invite this user to a selected group.', on_delete=django.db.models.deletion.CASCADE, related_name='pending_group_invitations', to=settings.AUTH_USER_MODEL, verbose_name='Invited user'),
        ),
        migrations.AlterField(
            model_name='pendingtask',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='auth.group'),
        ),
        migrations.AlterField(
            model_name='publishrequest',
            name='activation_until',
            field=models.DateTimeField(default=datetime.datetime(2021, 4, 15, 8, 4, 21, 896110, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='publishrequest',
            name='created_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.group'),
        ),
        migrations.AlterField(
            model_name='publishrequest',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pending_publish_requests', to='structure.mrmapgroup', verbose_name='group'),
        ),
        migrations.AlterField(
            model_name='publishrequest',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pending_publish_requests', to='structure.organization', verbose_name='organization'),
        ),
        migrations.AlterField(
            model_name='useractivation',
            name='activation_until',
            field=models.DateTimeField(default=datetime.datetime(2021, 4, 15, 8, 4, 21, 895025, tzinfo=utc)),
        ),
    ]
