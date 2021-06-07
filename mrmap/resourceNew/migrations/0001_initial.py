# Generated by Django 3.1.8 on 2021-06-07 14:07

import MrMap.validators
import django.contrib.gis.db.models.fields
from django.db import migrations, models
import main.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DatasetMetadata',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('access_constraints', models.TextField(default='', help_text='access constraints for the given resource.', verbose_name='access constraints')),
                ('fees', models.TextField(default='', help_text='Costs and of terms of use for the given resource.', verbose_name='fees')),
                ('use_limitation', models.TextField(default='')),
                ('license_source_note', models.TextField()),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_stamp', models.DateTimeField(auto_now_add=True, db_index=True, help_text='date that the metadata was created. If this is a metadata record which is parsed from remote iso metadata, the date stamp of the remote iso metadata will be used.', verbose_name='date stamp')),
                ('file_identifier', models.CharField(default='', editable=False, help_text='the parsed file identifier from the iso metadata xml (gmd:fileIdentifier) OR for example if it is a layer/featuretypethe uuid of the described layer/featuretype shall be used to identify the generated iso metadata xml.', max_length=1000, verbose_name='file identifier')),
                ('origin', models.CharField(choices=[(None, '---'), ('capabilities', 'capabilities'), ('iso metadata', 'iso metadata')], editable=False, help_text='Where the metadata record comes from.', max_length=20, verbose_name='origin')),
                ('origin_url', models.URLField(blank=True, editable=False, help_text='the url of the document where the information of this metadata record comes from', max_length=4096, null=True, verbose_name='origin url')),
                ('title', models.CharField(help_text='a short descriptive title for this metadata', max_length=1000, verbose_name='title')),
                ('abstract', models.TextField(default='', help_text='brief summary of the content of this metadata.', verbose_name='abstract')),
                ('is_broken', models.BooleanField(default=False, editable=False, help_text='TODO', verbose_name='is broken')),
                ('harvest_result', models.CharField(choices=[(None, '---'), ('fetched', 'fetched'), ('insufficient quality', 'insufficient quality'), ('successfully', 'successfully')], default='', editable=False, help_text='to determine errors while harvesting process. Get linked iso metadata from parsed capabilities result is also a harvesting process.', max_length=50, verbose_name='harvest result')),
                ('insufficient_quality', models.TextField(help_text='')),
                ('is_searchable', models.BooleanField(default=False, help_text='only searchable metadata will be returned from the search api', verbose_name='is searchable')),
                ('is_custom', models.BooleanField(default=False, editable=False)),
                ('hits', models.IntegerField(default=0, editable=False, help_text='how many times this metadata was requested by a client', verbose_name='hits')),
                ('spatial_res_type', models.CharField(choices=[('groundDistance', 'groundDistance'), ('scaleDenominator', 'groundDistance')], default='', help_text='Ground resolution in meter or the equivalent scale.', max_length=20, verbose_name='resolution type')),
                ('spatial_res_value', models.FloatField(blank=True, help_text='The value depending on the selected resolution type.', null=True, verbose_name='resolution value')),
                ('format', models.CharField(choices=[(None, '---'), ('Database', 'Database'), ('Esri shape', 'Esri shape'), ('CSV', 'CSV'), ('GML', 'GML'), ('GeoTIFF', 'GeoTIFF')], help_text='The format in which the described dataset is stored.', max_length=20, verbose_name='format')),
                ('charset', models.CharField(choices=[(None, '---'), ('utf8', 'utf8')], help_text='The charset which is used by the stored data.', max_length=10, verbose_name='charset')),
                ('inspire_top_consistence', models.BooleanField(default=False, help_text='Flag to signal if the described data has a topologically consistence.')),
                ('preview_image', models.ImageField(blank=True, null=True, upload_to='')),
                ('lineage_statement', models.TextField(blank=True, null=True)),
                ('update_frequency_code', models.CharField(blank=True, choices=[('annually', 'annually'), ('asNeeded', 'asNeeded'), ('biannually', 'biannually'), ('irregular', 'irregular'), ('notPlanned', 'notPlanned'), ('unknown', 'unknown')], max_length=20, null=True)),
                ('bounding_geometry', django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
                ('dataset_id', models.CharField(default='', help_text='identifier of the remote data', max_length=4096)),
                ('dataset_id_code_space', models.CharField(default='', help_text='code space for the given identifier', max_length=4096)),
                ('inspire_interoperability', models.BooleanField(default=False, help_text='flag to signal if this ')),
            ],
            options={
                'verbose_name': 'dataset metadata',
                'verbose_name_plural': 'dataset metadata',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='DatasetMetadataRelation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('relation_type', models.CharField(choices=[(None, '---'), ('visualizes', 'visualizes'), ('describes', 'describes'), ('harvestedThrough', 'harvestedThrough'), ('harvestedParent', 'harvestedParent'), ('publishedBy', 'publishedBy')], max_length=20)),
                ('is_internal', models.BooleanField(default=False, help_text='true means that this relation is created by a user and the dataset is maybe not linked in a capabilities document for example.', verbose_name='internal relation?')),
                ('origin', models.CharField(choices=[(None, '---'), ('Capabilities', 'Capabilities'), ('Upload', 'Upload'), ('Editor', 'Editor'), ('Catalogue', 'Catalogue')], help_text='determines where this relation was found or it is added by a user.', max_length=20, verbose_name='origin')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Dimension',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='the type of the content stored in extent field.', max_length=50, verbose_name='name')),
                ('units', models.CharField(help_text='measurement units specifier', max_length=50, verbose_name='units')),
                ('extent', models.TextField(help_text='The extent string declares what value(s) along the Dimension axis are appropriate for this specific geospatial data object.', verbose_name='extent')),
            ],
        ),
        migrations.CreateModel(
            name='ExternalAuthentication',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('username', models.CharField(help_text='the username used for the authentication.', max_length=255, verbose_name='username')),
                ('password', models.CharField(help_text='the password used for the authentication.', max_length=500, verbose_name='password')),
                ('auth_type', models.CharField(choices=[(None, '---'), ('http_basic', 'http_basic'), ('http_digest', 'http_digest'), ('none', 'none')], default='none', help_text='kind of authentication mechanism shall used.', max_length=100, verbose_name='authentication type')),
                ('test_url', models.URLField(help_text='this shall be the full get capabilities request url.', validators=[MrMap.validators.validate_get_capablities_uri], verbose_name='Service url')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='FeatureType',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('identifier', models.CharField(default='', editable=False, help_text='this is a string which identifies the element on the remote service.', max_length=500, verbose_name='identifier')),
                ('bbox_lat_lon', django.contrib.gis.db.models.fields.PolygonField(blank=True, editable=False, help_text='bounding box shall be supplied regardless of what CRS the map server may support, but it may be approximate if the data are not natively in geographic coordinates. The purpose of bounding box is to facilitate geographic searches without requiring coordinate transformations by the search engine.', null=True, srid=4326, verbose_name='bounding box')),
            ],
            options={
                'verbose_name': 'feature type',
                'verbose_name_plural': 'feature types',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='FeatureTypeElement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'verbose_name': 'feature type element',
                'verbose_name_plural': 'feature type elements',
                'ordering': ['-name'],
            },
        ),
        migrations.CreateModel(
            name='FeatureTypeMetadata',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_stamp', models.DateTimeField(auto_now_add=True, db_index=True, help_text='date that the metadata was created. If this is a metadata record which is parsed from remote iso metadata, the date stamp of the remote iso metadata will be used.', verbose_name='date stamp')),
                ('file_identifier', models.CharField(default='', editable=False, help_text='the parsed file identifier from the iso metadata xml (gmd:fileIdentifier) OR for example if it is a layer/featuretypethe uuid of the described layer/featuretype shall be used to identify the generated iso metadata xml.', max_length=1000, verbose_name='file identifier')),
                ('origin', models.CharField(choices=[(None, '---'), ('capabilities', 'capabilities'), ('iso metadata', 'iso metadata')], editable=False, help_text='Where the metadata record comes from.', max_length=20, verbose_name='origin')),
                ('origin_url', models.URLField(blank=True, editable=False, help_text='the url of the document where the information of this metadata record comes from', max_length=4096, null=True, verbose_name='origin url')),
                ('title', models.CharField(help_text='a short descriptive title for this metadata', max_length=1000, verbose_name='title')),
                ('abstract', models.TextField(default='', help_text='brief summary of the content of this metadata.', verbose_name='abstract')),
                ('is_broken', models.BooleanField(default=False, editable=False, help_text='TODO', verbose_name='is broken')),
                ('harvest_result', models.CharField(choices=[(None, '---'), ('fetched', 'fetched'), ('insufficient quality', 'insufficient quality'), ('successfully', 'successfully')], default='', editable=False, help_text='to determine errors while harvesting process. Get linked iso metadata from parsed capabilities result is also a harvesting process.', max_length=50, verbose_name='harvest result')),
                ('insufficient_quality', models.TextField(help_text='')),
                ('is_searchable', models.BooleanField(default=False, help_text='only searchable metadata will be returned from the search api', verbose_name='is searchable')),
                ('is_custom', models.BooleanField(default=False, editable=False)),
                ('hits', models.IntegerField(default=0, editable=False, help_text='how many times this metadata was requested by a client', verbose_name='hits')),
            ],
            options={
                'verbose_name': 'feature type metadata',
                'verbose_name_plural': 'feature type metadata',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='HarvestResult',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Keyword',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyword', models.CharField(db_index=True, max_length=255, unique=True)),
            ],
            options={
                'ordering': ['keyword'],
            },
        ),
        migrations.CreateModel(
            name='Layer',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('identifier', models.CharField(default='', editable=False, help_text='this is a string which identifies the element on the remote service.', max_length=500, verbose_name='identifier')),
                ('bbox_lat_lon', django.contrib.gis.db.models.fields.PolygonField(blank=True, editable=False, help_text='bounding box shall be supplied regardless of what CRS the map server may support, but it may be approximate if the data are not natively in geographic coordinates. The purpose of bounding box is to facilitate geographic searches without requiring coordinate transformations by the search engine.', null=True, srid=4326, verbose_name='bounding box')),
                ('is_queryable', models.BooleanField(default=False, editable=False, help_text='flag to signal if this layer provides factual information or not. Parsed from capabilities.', verbose_name='is queryable')),
                ('is_opaque', models.BooleanField(default=False, editable=False, help_text='flag to signal if this layer support transparency content or not. Parsed from capabilities.', verbose_name='is opaque')),
                ('is_cascaded', models.BooleanField(default=False, editable=False, help_text='WMS cascading allows to expose layers coming from other WMS servers as if they were local layers', verbose_name='is cascaded')),
                ('scale_min', models.FloatField(blank=True, help_text='minimum scale for a possible request to this layer. If the request is out of the given scope, the service will response with empty transparentimages. None value means no restriction.', null=True, verbose_name='scale minimum value')),
                ('scale_max', models.FloatField(blank=True, help_text='maximum scale for a possible request to this layer. If the request is out of the given scope, the service will response with empty transparentimages. None value means no restriction.', null=True, verbose_name='scale maximum value')),
                ('lft', models.PositiveIntegerField(editable=False)),
                ('rght', models.PositiveIntegerField(editable=False)),
                ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
                ('level', models.PositiveIntegerField(editable=False)),
            ],
            options={
                'verbose_name': 'layer',
                'verbose_name_plural': 'layers',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='LayerMetadata',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_stamp', models.DateTimeField(auto_now_add=True, db_index=True, help_text='date that the metadata was created. If this is a metadata record which is parsed from remote iso metadata, the date stamp of the remote iso metadata will be used.', verbose_name='date stamp')),
                ('file_identifier', models.CharField(default='', editable=False, help_text='the parsed file identifier from the iso metadata xml (gmd:fileIdentifier) OR for example if it is a layer/featuretypethe uuid of the described layer/featuretype shall be used to identify the generated iso metadata xml.', max_length=1000, verbose_name='file identifier')),
                ('origin', models.CharField(choices=[(None, '---'), ('capabilities', 'capabilities'), ('iso metadata', 'iso metadata')], editable=False, help_text='Where the metadata record comes from.', max_length=20, verbose_name='origin')),
                ('origin_url', models.URLField(blank=True, editable=False, help_text='the url of the document where the information of this metadata record comes from', max_length=4096, null=True, verbose_name='origin url')),
                ('title', models.CharField(help_text='a short descriptive title for this metadata', max_length=1000, verbose_name='title')),
                ('abstract', models.TextField(default='', help_text='brief summary of the content of this metadata.', verbose_name='abstract')),
                ('is_broken', models.BooleanField(default=False, editable=False, help_text='TODO', verbose_name='is broken')),
                ('harvest_result', models.CharField(choices=[(None, '---'), ('fetched', 'fetched'), ('insufficient quality', 'insufficient quality'), ('successfully', 'successfully')], default='', editable=False, help_text='to determine errors while harvesting process. Get linked iso metadata from parsed capabilities result is also a harvesting process.', max_length=50, verbose_name='harvest result')),
                ('insufficient_quality', models.TextField(help_text='')),
                ('is_searchable', models.BooleanField(default=False, help_text='only searchable metadata will be returned from the search api', verbose_name='is searchable')),
                ('is_custom', models.BooleanField(default=False, editable=False)),
                ('hits', models.IntegerField(default=0, editable=False, help_text='how many times this metadata was requested by a client', verbose_name='hits')),
                ('preview_image', models.ImageField(blank=True, null=True, upload_to='')),
            ],
            options={
                'verbose_name': 'layer metadata',
                'verbose_name_plural': 'layer metadata',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='LegendUrl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('legend_url', models.URLField(editable=False, help_text='contains the location of an image of a map legend appropriate to the enclosing Style.', max_length=4096)),
                ('height', models.IntegerField(editable=False, help_text='the size of the image in pixels')),
                ('width', models.IntegerField(editable=False, help_text='the size of the image in pixels')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Licence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('symbol_url', models.URLField(null=True)),
                ('description', models.TextField()),
                ('description_url', models.URLField(null=True)),
                ('is_open_data', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='MetadataContact',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('person_name', models.CharField(blank=True, default='', max_length=200, null=True, verbose_name='Contact person')),
                ('email', models.EmailField(blank=True, default='', max_length=100, null=True, verbose_name='E-Mail')),
                ('phone', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Phone')),
                ('facsimile', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Facsimile')),
                ('city', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='City')),
                ('postal_code', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Postal code')),
                ('address_type', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address type')),
                ('address', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address')),
                ('state_or_province', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='State or province')),
                ('country', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Country')),
                ('name', models.CharField(default='', help_text='The name of the organization', max_length=256, verbose_name='Name')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='MimeType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mime_type', models.CharField(db_index=True, help_text='The Internet Media Type', max_length=500, unique=True, verbose_name='mime type')),
            ],
        ),
        migrations.CreateModel(
            name='OperationUrl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('method', models.CharField(choices=[(None, '---'), ('Get', 'Get'), ('Post', 'Post')], help_text='the http method you can perform for this url', max_length=10, verbose_name='http method')),
                ('url', models.URLField(editable=False, help_text='the url for this operation', max_length=4096, verbose_name='url')),
                ('operation', models.CharField(choices=[(None, '---'), ('GetCapabilities', 'GetCapabilities'), ('GetMap', 'GetMap'), ('GetFeatureInfo', 'GetFeatureInfo'), ('DescribeLayer', 'DescribeLayer'), ('GetLegendGraphic', 'GetLegendGraphic'), ('GetStyles', 'GetStyles'), ('PutStyles', 'PutStyles'), ('GetFeature', 'GetFeature'), ('Transaction', 'Transaction'), ('LockFeature', 'LockFeature'), ('DescribeFeatureType', 'DescribeFeatureType'), ('GetFeatureWithLock', 'GetFeatureWithLock'), ('GetGmlObject', 'GetGmlObject'), ('ListStoredQueries', 'ListStoredQueries'), ('GetPropertyValue', 'GetPropertyValue'), ('DescribeStoredQueries', 'DescribeStoredQueries'), ('GetRecords', 'GetRecords'), ('DescribeRecord', 'DescribeRecord'), ('GetRecordById', 'GetRecordById')], editable=False, help_text='the operation you can perform with this url.', max_length=30, verbose_name='operation')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ReferenceSystem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100)),
                ('prefix', models.CharField(choices=[(None, '---'), ('EPSG', 'EPSG')], default='EPSG', max_length=255)),
            ],
            options={
                'ordering': ['-code'],
            },
        ),
        migrations.CreateModel(
            name='RemoteMetadata',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('link', models.URLField(help_text='the url where the metadata could be downloaded from.', max_length=4094, verbose_name='download link')),
                ('remote_content', models.TextField(help_text='the fetched content of the download url.', null=True, verbose_name='remote content')),
                ('object_id', models.UUIDField(help_text='the uuid of the described service, layer or feature type', verbose_name='described resource')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=False, help_text='Used to activate/deactivate the service. If it is deactivated, you cant request the resource through the Mr. Map proxy.', verbose_name='is active')),
            ],
            options={
                'verbose_name': 'service',
                'verbose_name_plural': 'services',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ServiceMetadata',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('access_constraints', models.TextField(default='', help_text='access constraints for the given resource.', verbose_name='access constraints')),
                ('fees', models.TextField(default='', help_text='Costs and of terms of use for the given resource.', verbose_name='fees')),
                ('use_limitation', models.TextField(default='')),
                ('license_source_note', models.TextField()),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_stamp', models.DateTimeField(auto_now_add=True, db_index=True, help_text='date that the metadata was created. If this is a metadata record which is parsed from remote iso metadata, the date stamp of the remote iso metadata will be used.', verbose_name='date stamp')),
                ('file_identifier', models.CharField(default='', editable=False, help_text='the parsed file identifier from the iso metadata xml (gmd:fileIdentifier) OR for example if it is a layer/featuretypethe uuid of the described layer/featuretype shall be used to identify the generated iso metadata xml.', max_length=1000, verbose_name='file identifier')),
                ('origin', models.CharField(choices=[(None, '---'), ('capabilities', 'capabilities'), ('iso metadata', 'iso metadata')], editable=False, help_text='Where the metadata record comes from.', max_length=20, verbose_name='origin')),
                ('origin_url', models.URLField(blank=True, editable=False, help_text='the url of the document where the information of this metadata record comes from', max_length=4096, null=True, verbose_name='origin url')),
                ('title', models.CharField(help_text='a short descriptive title for this metadata', max_length=1000, verbose_name='title')),
                ('abstract', models.TextField(default='', help_text='brief summary of the content of this metadata.', verbose_name='abstract')),
                ('is_broken', models.BooleanField(default=False, editable=False, help_text='TODO', verbose_name='is broken')),
                ('harvest_result', models.CharField(choices=[(None, '---'), ('fetched', 'fetched'), ('insufficient quality', 'insufficient quality'), ('successfully', 'successfully')], default='', editable=False, help_text='to determine errors while harvesting process. Get linked iso metadata from parsed capabilities result is also a harvesting process.', max_length=50, verbose_name='harvest result')),
                ('insufficient_quality', models.TextField(help_text='')),
                ('is_searchable', models.BooleanField(default=False, help_text='only searchable metadata will be returned from the search api', verbose_name='is searchable')),
                ('is_custom', models.BooleanField(default=False, editable=False)),
                ('hits', models.IntegerField(default=0, editable=False, help_text='how many times this metadata was requested by a client', verbose_name='hits')),
            ],
            options={
                'verbose_name': 'service metadata',
                'verbose_name_plural': 'service metadata',
            },
            bases=(main.models.GenericModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ServiceType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(choices=[(None, '---'), ('wms', 'wms'), ('wfs', 'wfs'), ('wmc', 'wmc'), ('dataset', 'dataset'), ('csw', 'csw')], editable=False, help_text='the concrete type name of the service type.', max_length=10, verbose_name='type')),
                ('version', models.CharField(choices=[(None, '---'), ('1.0.0', '1.0.0'), ('1.1.0', '1.1.0'), ('1.1.1', '1.1.1'), ('1.3.0', '1.3.0'), ('2.0.0', '2.0.0'), ('2.0.2', '2.0.2')], editable=False, help_text='the version of the service type as sem version', max_length=10, verbose_name='version')),
                ('specification', models.URLField(editable=False, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Style',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('name', models.CharField(editable=False, help_text="The style's Name is used in the Map request STYLES parameter to lookup the style on server side.", max_length=255, verbose_name='name')),
                ('title', models.CharField(editable=False, help_text='The Title is a human-readable string as an alternative for the name attribute.', max_length=255, verbose_name='title')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
