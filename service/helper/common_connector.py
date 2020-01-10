"""
Author: Armin Retterath
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: armin.retterath@vermkv.rlp.de

"""
import time

# Problem of unresolved python c extensions: https://stackoverflow.com/questions/41598399/pydev-tags-import-as-unresolved-import-all-compiled-extensions
import pycurl
import urllib
from urllib.parse import urlencode

import requests
import types

import re

from service.settings import DEFAULT_CONNECTION_TYPE, REQUEST_TIMEOUT
from MapSkinner.settings import HTTP_PROXY, PROXIES
from service.helper.enums import ConnectionEnum

try:
    from io import BytesIO
except ImportError:
    import StringIO as BytesIO


class CommonConnector:
    def __init__(self, url=None, external_auth=None, connection_type=None):
        self._url = None
        self.external_auth = external_auth
        self.connection_type = connection_type if connection_type is not None else DEFAULT_CONNECTION_TYPE
        self.init_time = time.time()
        self.run_time = None
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
        self.is_local_request = False

        if url is not None:
            self.set_url(url)

    def set_url(self, url: str):
        """ Setter for url parameter

        Args:
            url (str):
        Returns:
             nothing
        """
        url_obj = urllib.parse.urlparse(url)
        if "127.0.0.1" in url_obj.hostname or "localhost" in url_obj.hostname:
            self.is_local_request = True
        self._url = url

    def load(self, params: dict = None):
        self.init_time = time.time()
        if self.connection_type is ConnectionEnum.CURL:
            response = self.__load_curl(params)
        elif self.connection_type is ConnectionEnum.REQUESTS:
            response = self.__load_requests(params)
            self.status_code = response.status_code
        else:
            response = self.__load_urllib()
        # parse response
        self.content = response.content
        self.encoding = response.encoding
        self.text = response.text
        self.run_time = time.time() - self.init_time

    def __load_curl(self, params: dict = None):
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

        url_args = ""
        if params is not None:
            url_args = "?" +urlencode(params)

        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, self._url + url_args)
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
    
    def __load_requests(self, params: dict = None):
        response = None
        proxies = None
        if len(PROXIES) > 0 and not self.is_local_request:
            proxies = PROXIES
        if self.external_auth is not None:
            if self.external_auth.auth_type is None:
                response = requests.request(self.http_method, self._url, params=params, proxies=proxies, timeout=REQUEST_TIMEOUT)
            elif self.external_auth.auth_type == 'http_basic':
                from requests.auth import HTTPBasicAuth
                response = requests.request(self.http_method, self._url, params=params, auth=HTTPBasicAuth(self.external_auth.username, self.external_auth.password), proxies=proxies, timeout=REQUEST_TIMEOUT)
            elif self.external_auth.auth_type == 'http_digest':
                from requests.auth import HTTPDigestAuth
                response = requests.request(self.http_method, self._url, params=params, auth=HTTPDigestAuth(self.external_auth.username, self.external_auth.password), proxies=proxies, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.request(self.http_method, self._url, params=params, proxies=proxies, timeout=REQUEST_TIMEOUT)
        else:
            response = requests.request(self.http_method, self._url, params=params, proxies=proxies, timeout=REQUEST_TIMEOUT)

        return response   
    
    def __load_urllib(self):
        pass

    def post(self, data):
        """ Wraps the post functionality of different request implementations (CURL, Requests).

        The response is written to self.content.

        Args:
            data (dict|byte): The post data body
        Returns:
             nothing
        """
        self.init_time = time.time()

        if self.connection_type is ConnectionEnum.CURL:
            # perform curl post
            pass
        elif self.connection_type is ConnectionEnum.REQUESTS:
            # perform requests post
            response = requests.post(
                self._url,
                data,
                timeout=REQUEST_TIMEOUT,
                proxies=PROXIES
            )
            self.content = response.content
        else:
            # something
            pass
        self.run_time = time.time() - self.init_time
