from django.db import models
from django.contrib.gis.db import models
from structure.models import User, Group, UserGroupRoleRel, Organization

class Category(models.Model):
    title_DE = models.CharField(max_length=100, unique=True)
    title_EN = models.CharField(max_length=100, unique=True)
    description_DE = models.CharField(max_length=100, unique=True)
    description_EN = models.CharField(max_length=100, unique=True)
    is_inspire = models.BooleanField()
    symbol = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField()
    created = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)

class ServiceType(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    specification = models.URLField(blank=False, null=False)

class Service(models.Model):
    title = models.CharField(max_length=100, unique=True)
    abstract = models.CharField(max_length=1000)
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Group, on_delete=models.DO_NOTHING)
    # published_for = models.ForeignKey(Organization, on_delete=models.DO_NOTHING)
    # supportedVersions = models.CharField(max_length=1000) # json encoded
    servicetype = models.ForeignKey(ServiceType, on_delete=models.DO_NOTHING)
    categories = models.ManyToManyField(Category)

    class Meta:
        abstract = True

class WMS(Service):
    availability = models.DecimalField(decimal_places=2, max_digits=4)
    is_available = models.BooleanField()

class Layer(WMS):
    hits = models.IntegerField()
    preview_image = models.CharField(max_length=100)
    preview_extend = models.CharField(max_length=100)
    preview_legend = models.CharField(max_length=100)
    parent = models.ForeignKey("self", on_delete=models.DO_NOTHING)
    position = models.IntegerField()
    is_queryable = models.BooleanField()
    is_opaque = models.BooleanField()
    is_cascaded = models.BooleanField()
    scale_min = models.FloatField()
    scale_max = models.FloatField()
    bbox_lat_lon = models.CharField(max_length=255)
    #bbox_srs = models.CharField(max)


class WFS(Service):
    availability = models.DecimalField(decimal_places=2, max_digits=4)
    is_available = models.BooleanField()

class Module(WFS):
    type = models.CharField(max_length=100)

class Dataset(models.Model):
    time_begin = models.DateTimeField()
    time_end = models.DateTimeField()

class Keyword(models.Model):
    keyword = models.CharField(max_length=100)

class Metadata(models.Model):
    uuid = models.CharField(max_length=100)
    title = models.CharField(max_length=100)
    abstract = models.CharField(max_length=1000)
    online_resource = models.CharField(max_length=100)
    keyword = models.ForeignKey(Keyword, on_delete=models.DO_NOTHING)

class TermsOfUse(models.Model):
    name = models.CharField(max_length=100)
    symbol_url = models.CharField(max_length=100)
    description = models.CharField(max_length=100)
    is_open_data = models.BooleanField()
    fees = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    created = models.DateTimeField()

class ServiceMetadata(Metadata):
    contact_person = models.CharField(max_length=100)
    contact_person_position = models.CharField(max_length=100)
    contact_organization = models.CharField(max_length=100)
    address_type = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state_or_province = models.CharField(max_length=100)
    post_code = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=100)
    contact_email = models.CharField(max_length=100)
    terms_of_use = models.ForeignKey(TermsOfUse, on_delete=models.DO_NOTHING)
    access_constraints = models.CharField(max_length=200)
    created = models.DateTimeField()
    last_change = models.DateTimeField()
    status = models.IntegerField()
    last_harvest_successful = models.BooleanField()
    last_harvest_exception = models.CharField(max_length=200)
    export_to_csw = models.BooleanField()
    spatial_res_type = models.CharField(max_length=100)
    spatial_res_value = models.CharField(max_length=100)
    is_active = models.BooleanField()
    is_inspire_conform = models.BooleanField()
    has_inspire_downloads = models.BooleanField()
    geom = models.GeometryField()
    bounding_geometry = models.GeometryField()
    service_wms = models.ForeignKey(WMS, null=True, blank=True, on_delete=models.DO_NOTHING)
    service_wfs = models.ForeignKey(WFS, null=True, blank=True, on_delete=models.DO_NOTHING)

class ReferenceSystem(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100)

class ContentMetadata(Metadata):
    bbox = models.DecimalField(decimal_places=2, max_digits=4)
    reference_system = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING)
    dimension = models.CharField(max_length=100)
    authority_url = models.CharField(max_length=100)
    identifier = models.CharField(max_length=100)
    metadata_url = models.CharField(max_length=100)
    dataset = models.ForeignKey(Dataset,  on_delete=models.DO_NOTHING)
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)