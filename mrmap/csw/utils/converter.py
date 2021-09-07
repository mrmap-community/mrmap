"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from abc import abstractmethod
from collections import OrderedDict
from lxml.etree import Element, QName
from django.utils import timezone
from django.db.models import QuerySet

from MrMap.settings import XML_NAMESPACES, GENERIC_NAMESPACE_TEMPLATE
from csw.utils.parameter import ParameterResolver

GMD_SCHEMA = "http://www.isotc211.org/2005/gmd"
IDENTIFIER_TEMPLATE = "{}identifier"
TITLE_TEMPLATE = "{}title"
TYPE_TEMPLATE = "{}type"
DATE_STRF = "%Y-%m-%d"

