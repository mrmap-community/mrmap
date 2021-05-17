# Generated by Django 3.1.8 on 2021-05-04 17:09

from django.db import migrations
import django.db.models.expressions


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0002_auto_20210504_0939'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pendingtask',
            options={'ordering': [django.db.models.expressions.Case(django.db.models.expressions.When(status='STARTED', then=0), django.db.models.expressions.When(status='PENDING', then=1), django.db.models.expressions.When(status='FAILURE', then=2), django.db.models.expressions.When(status='SUCCESS', then=3)), '-date_done', '-task_id']},
        ),
    ]