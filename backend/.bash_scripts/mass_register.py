# usage: python mass_register.py services.txt
import json
import sys

import requests
import urllib3

urllib3.disable_warnings()


host = "https://localhost/"
endpoint = "api/v1/registry/ogcservices/"

# example:e165337d7cb46cd625d4f23435962a344d5f1aa0
token = "26f91c14e069beaa98e478a48f2769ec70cd07ef"

headers = {
    'accept': 'application/vnd.api+json',
    'Content-Type': 'application/vnd.api+json'
    # 'Authorization': 'Token '+token
}

# register parameters
owner = "71ea1bd8-a9b0-4e15-a5ad-abbe8d403217"  # uuid
# TODO
service_authentication = None

#  read wms file
with open(sys.argv[1]) as f:
    lines = [line.rstrip() for line in f]

request_body = {
    "data": {
        "type": "OgcService",
        "attributes": {
            "get_capabilities_url": "http://www.komserv4gdi.service24.rlp.de/ows/wms/07334016_Leimersheim?VERSION=1.1.1&SERVICE=WMS&REQUEST=GetCapabilities"
        },
        "relationships": {
            "owner": {
                "data": {"type": "Organization", "id": owner}
            }
        }
    }
}

for url in lines:
    request_body['data']['attributes']['get_capabilities_url'] = url
    r = requests.post(
        url=host + endpoint,
        data=json.dumps(request_body),
        headers=headers,
        verify=False)
    print(r.status_code)
    if r.status_code != 202:
        print(r.content)
