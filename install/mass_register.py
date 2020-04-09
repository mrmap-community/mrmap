# usage: python mass_register.py MyWmsList.txt
import requests
import urllib
from enum import Enum
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import sys

host="https://127.0.0.1"
user="root"
pw="root"

def resolve_service_enum(service: str):
    """ Returns the matching Enum for a given service as string

    Args:
        service(str): The version as string
    Returns:
         The matching enum, otherwise None
    """
    if service is None:
        return None
    for enum in OGCServiceEnum:
        if str(enum.value).upper() == service.upper():
            return enum.value
    return None

class OGCServiceEnum(Enum):
    """ Defines all supported service types

    """

    WMS = "wms"
    WFS = "wfs"
    WMC = "wmc"
    DATASET = "dataset"

def split_service_uri(uri):

    ret_dict = {}
    cap_url_dict = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(uri).query))
    tmp = {}

    # remove duplicate parameters
    service_keywords = [
        "REQUEST",
        "SERVICE",
        "VERSION"
    ]

    for param_key, param_val in cap_url_dict.items():
        p = param_key.upper()
        if p not in tmp:
            tmp[p] = param_val

    cap_url_query = urllib.parse.urlsplit(uri).query
    ret_dict["service"] = resolve_service_enum(tmp.get("SERVICE", None))
    ret_dict["request"] = tmp.get("REQUEST", None)
    ret_dict["version"] = tmp.get("VERSION", None)
    ret_dict["base_uri"] = uri.replace(cap_url_query, "")
    additional_params = []

    # append additional parameters back to the base uri
    for param_key, param_val in cap_url_dict.items():
        if param_key.upper() not in service_keywords:
            additional_params.append(param_key + "=" + param_val)

    ret_dict["base_uri"] += "&".join(additional_params)
    return ret_dict

#  read wms file
with open(sys.argv[1]) as f:
    lines = [line.rstrip() for line in f]

cookies = {
}

data1 = [
  ('username', user),
  ('next', ''),
  ('next', ''),
  ('next', ''),
  ('next', ''),
  ('password', pw),
]

#login
r1 = requests.post(host, cookies=cookies, data=data1, verify=False)

#example
data2 = {
  'page': '2',
  'is_form_update': 'False',
  'ogc_request': 'GetCapabilities',
  'ogc_service': 'wms',
  'ogc_version': '1.1.1',
  'uri': 'http://www.komserv4gdi.service24.rlp.de/ows/wms/07334016_Leimersheim?VERSION=1.1.1&SERVICE=WMS&REQUEST=GetCapabilities',
  'registering_with_group': 1,
  'registering_for_other_organization': ''
}

# make register requests

for url in lines:
    url_dict = split_service_uri(url)
    data2['ogc_request'] = url_dict["request"]
    data2['ogc_version'] = url_dict["version"]
    data2['ogc_service'] = url_dict["service"]
    data2['uri'] = url_dict["base_uri"]
    r2 = requests.post(host+'/service/add/', cookies=r1.cookies, data=data2, verify=False)
    #req = session.post(host+"/service/add", data={'REQUEST': 'GetCapabilities' ,'SERVICE': 'WMS','page': 2, 'is_form_update': False, 'ogc_request': 'GetCapabilities', 'ogc_service': 'wms','ogc_version': '1.1.1','registering_with_group': 1,'registering_for_other_organization': '','uri': url}, verify=False)
    print("registering: " +url)
