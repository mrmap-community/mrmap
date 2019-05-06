import uuid
from django.db import models
#from organiszations.models import Organization
from django.contrib.auth.models import User
#from metadata_registry.models import Metadata
# Create your models here.
class CommonResourceMetadata(models.Model):
    
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(max_length=1024, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now=False, auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, auto_now_add=False)
    deleted = models.DateTimeField(null=True, blank=True, editable=False)
    #metadata = models.ForeignKey(Metadata, null=True, blank=True, editable=False)
    #uri = models.CharField(max_length=1024, null=True, blank=True, editable=False)
    #resource_type = 'test' #webservice, ...
    
    class Meta:
        abstract = True
        
class CommonResourceOwnershipInfo(models.Model):
    
    owner = models.ForeignKey(User, null=True, blank=True, editable=False, on_delete=models.CASCADE)
    #organization = models.ForeignKey(Organization)
    
    class Meta:
        abstract = True
        