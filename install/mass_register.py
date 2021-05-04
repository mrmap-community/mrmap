# usage: python mass_register.py MyWmsList.txt
import requests
import urllib
from enum import Enum
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import sys

host="http://127.0.0.1:8000"
# generate a token on the web interface and insert it here
token="48352aa811420064c14286e4dd91c4383d79594a" # example:e165337d7cb46cd625d4f23435962a344d5f1aa0

# register parameters
registering_for_organization = "44375800-22cd-4b91-a5a1-a939713b42fb"  # int
external_authentication = False # bool
external_username = "" # str
external_password = "" #str
external_auth_type = "" # str, http_digest or http_basic


#  read wms file
with open(sys.argv[1]) as f:
    lines = [line.rstrip() for line in f]


#example
data = {
  'uri': 'http://www.komserv4gdi.service24.rlp.de/ows/wms/07334016_Leimersheim?VERSION=1.1.1&SERVICE=WMS&REQUEST=GetCapabilities', #example
  'for-org': registering_for_organization,
  'ext-auth': external_authentication,
  'ext-username': external_username,
  'ext-password': external_password,
  'ext-auth-type': external_auth_type
}

# make register requests

for url in lines:
    data['uri'] = url
    r = requests.post(host+'/api/service/', data=data, headers={'Authorization': 'Token '+token}, verify=False)
    print(r.status_code)
    #req = session.post(host+"/service/add", data={'REQUEST': 'GetCapabilities' ,'SERVICE': 'WMS','page': 2, 'is_form_update': False, 'ogc_request': 'GetCapabilities', 'ogc_service': 'wms','ogc_version': '1.1.1','registering_with_group': 1,'registering_for_other_organization': '','uri': url}, verify=False)
    print("registering: " +url)
