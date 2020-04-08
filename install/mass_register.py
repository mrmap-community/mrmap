import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import sys

host="http://127.0.0.1"
user="root"
pw="root"

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

data2 = {
  'page': '2',
  'is_form_update': 'False',
  'ogc_request': 'GetCapabilities',
  'ogc_service': 'wms',
  'ogc_version': '1.1.1',
  'uri': '',
  'registering_with_group': 1,
  'registering_for_other_organization': ''
}

# make register requests
for url in lines:
    data2['uri'] = url
    r2 = requests.post(host+'/service/add/', cookies=r1.cookies, data=data2, verify=False)
    #req = session.post(host+"/service/add", data={'REQUEST': 'GetCapabilities' ,'SERVICE': 'WMS','page': 2, 'is_form_update': False, 'ogc_request': 'GetCapabilities', 'ogc_service': 'wms','ogc_version': '1.1.1','registering_with_group': 1,'registering_for_other_organization': '','uri': url}, verify=False)
    print("registering: "+url)
