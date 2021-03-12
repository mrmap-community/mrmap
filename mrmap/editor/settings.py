"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 11.11.19

"""
import logging

editor_logger = logging.getLogger('MrMap.editor')

""" WMS SECURED OPERATIONS

If a group is allowed to perform the operation 'GetFeatureInfo', it must(!) be allowed for 'GetMap' as well. 
Calling 'GetFeatureInfo' without calling 'GetMap' is nonsense. 

"""
WMS_SECURED_OPERATIONS = {
    "GetFeatureInfo",
    "GetMap",
}

""" WFS SECURED OPERATIONS

Allowing 'GetFeature' includes allowing of the operations
    * DescribeFeatureType
    * GetPropertyValue
    * LockFeature
    * GetGmlObject
    * GetFeatureWithLock

"""
WFS_SECURED_OPERATIONS = {
    "GetFeature",
    "Transaction",
}
