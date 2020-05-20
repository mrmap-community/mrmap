"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.db.models import QuerySet

from csw.utils.parameter import ParameterResolver


class MetadataConverter:
    """ Creates xml representations from given metadata

    For our use case we only support the regular Dublin Core and MD_Metadata style

    """
    def __init__(self, param: ParameterResolver, all_md: QuerySet):
        self.param = param
        self.all_md = all_md

    def convert_to_xml(self):
        pass