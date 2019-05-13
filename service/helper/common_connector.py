import time    

# Problem of unresolved python c extensions: https://stackoverflow.com/questions/41598399/pydev-tags-import-as-unresolved-import-all-compiled-extensions
import pycurl
import requests
import types

import re
from MapSkinner.settings import DEFAULT_CONNECTION_TYPE, HTTP_PROXY, REQUEST_PROXIES
from service.helper.enums import ConnectionType

try:
    from io import BytesIO
except ImportError:
    import StringIO as BytesIO


class CommonConnector():
    def __init__(self, url=None, auth=None, connection_type=None):
        self.url = url
        self.auth = auth
        self.connection_type = connection_type if connection_type is not None else DEFAULT_CONNECTION_TYPE
        self.init_time = time.time()
        self.load_time = None
        self.timeout = 5
        self.http_method = 'GET'
        self.http_version = '1.0'
        self.http_post_data = None
        self.http_content_type = None
        self.http_post_field_numbers = None
        self.http_external_headers = None
        self.http_send_custom_headers = False
        self.http_cookie_session = None
        self.content = None
        self.encoding = None
        self.text = None
        self.status_code = None
        
    def load(self):
        self.init_time = time.time()
        # print(self.http_method)
        c = ConnectionType.CURL
        if self.connection_type is ConnectionType.CURL:
            response = self.__load_curl()
        elif self.connection_type is ConnectionType.REQUESTS:
            response = self.__load_requests()
        else:
            response = self.__load_urllib()
        # parse response
        self.status_code = response.status_code
        self.content = response.content
        self.encoding = response.encoding
        self.text = response.text
        self.load_time = time.time() - self.init_time
        
    def __load_curl(self):
        response = types.SimpleNamespace()
        # Example from http://pycurl.io/docs/latest/quickstart.html
        #import curl #normally we would use pycurl - but the class has been renamed?
        #import re
        #try:
        #    from io import BytesIO
        #except ImportError:
        #    from StringIO import StringIO as BytesIO

        headers = {}
        def header_function(header_line):
            # HTTP standard specifies that headers are encoded in iso-8859-1.
            # On Python 2, decoding step can be skipped.
            # On Python 3, decoding step is required.
            header_line = header_line.decode('iso-8859-1')

            # Header lines include the first status line (HTTP/1.x ...).
            # We are going to ignore all lines that don't have a colon in them.
            # This will botch headers that are split on multiple lines...
            if ':' not in header_line:
                return

            # Break the header line into header name and value.
            name, value = header_line.split(':', 1)

            # Remove whitespace that may be present.
            # Header lines include the trailing newline, and there may be whitespace
            # around the colon.
            name = name.strip()
            value = value.strip()

            # Header names are case insensitive.
            # Lowercase name here.
            name = name.lower()

            # Now we can actually record the header name and value.
            # Note: this only works when headers are not duplicated, see below.
            headers[name] = value

        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, self.url)
        c.setopt(c.WRITEFUNCTION, buffer.write)
        # Set our header function.
        c.setopt(c.HEADERFUNCTION, header_function)
        # Check for proxies
        if HTTP_PROXY is not None:
            c.setopt(pycurl.PROXY, HTTP_PROXY)
        c.perform()
        c.close()

        # Figure out what encoding was sent with the response, if any.
        # Check against lowercased header name.
        encoding = None
        if 'content-type' in headers:
            content_type = headers['content-type'].lower()
            match = re.search('charset=(\S+)', content_type)
            if match:
                encoding = match.group(1)
                print('Decoding using %s' % encoding)
                
        if encoding is None:
            # Default encoding for HTML is iso-8859-1.
            # Other content types may have different default encoding,
            # or in case of binary data, may have no encoding at all.
            encoding = 'iso-8859-1'
            print('Assuming encoding is %s' % encoding)

        response.content = buffer.getvalue()
        response.encoding = encoding
        response.text = response.content.decode(encoding)
        return response
    
    def __load_requests(self):
        response = None
        proxies = None
        if len(REQUEST_PROXIES) > 0:
            proxies = REQUEST_PROXIES
        if self.auth is not None:
            if self.auth["auth_type"] == 'none':
                response = requests.request(self.http_method, self.url, proxies=proxies)
            elif self.auth["auth_type"] == 'http_basic':
                from requests.auth import HTTPBasicAuth
                response = requests.request(self.http_method, self.url, auth=HTTPBasicAuth(self.auth["auth_user"], self.auth["auth_password"]), proxies=proxies)
            elif self.auth["auth_type"] == 'http_digest':   
                from requests.auth import HTTPDigestAuth
                response = requests.request(self.http_method, self.url, auth=HTTPDigestAuth(self.auth["auth_user"], self.auth["auth_password"]), proxies=proxies)
            else:
                response = requests.request(self.http_method, self.url, proxies=proxies)
        else:
            response = requests.request(self.http_method, self.url, proxies=proxies)
        return response   
    
    def __load_urllib(self):
        pass
