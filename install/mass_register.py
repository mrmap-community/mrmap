import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

host="https://192.168.56.111"
user="root"
pw="root"

#  read wms file
with open('wmslist') as f:
    lines = [line.rstrip() for line in f]

# enable session <3
session = requests.Session()
# perform login
req = session.post(host, data={'username': user, 'next': '', 'password': pw, 'next': '','next': '','next': ''}, verify=False)
# make register requests
for url in lines:
    req = session.post(host+"/service/add", data={'page': 2, 'is_form_update': False, 'ogc_request': 'GetCapabilities', 'ogc_service': 'wms','ogc_version': '1.1.1','registering_with_group': 1,'registering_for_other_organization': '','uri': url}, verify=False)
    print("registering: "+url)
