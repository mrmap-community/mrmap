from django.apps import apps
from django.db import migrations, models
from django.db.models import F


def exchange_fields_values(app, schema):
    MyModel = apps.get_model('registry', 'MapContextLayer')

    # first, titles that are NULL, should be filled to avoid not.null constraint error when changing values
    MyModel.objects.get(title=None).update(title='')

    # now exchange the values between the columns
    MyModel.objects.all().update(title=F('name'), name=F('title'))
    # names = MyModel.objects.get(F('name'))
    # print(titles)
    # print(names)
    # MyModel.objects.all().update(title=names)
    # MyModel.objects.all().update(name=titles)


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0004_mapcontextlayer_is_leaf'),
    ]

    operations = [migrations.RunPython(exchange_fields_values), ]
