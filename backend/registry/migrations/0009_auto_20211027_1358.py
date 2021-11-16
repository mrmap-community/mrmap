from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('registry', '0008_mapcontextlayer_layer_style'),
    ]

    operations = [
        migrations.RenameField('mapcontextlayer', 'layer', 'rendering_layer'),
    ]
