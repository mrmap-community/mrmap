"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.02.20

"""
import json

from django.core.cache import cache

from service.helper.crypto_handler import CryptoHandler


class SimpleCacher:

    def __init__(self, ttl: int, key_prefix: str = None):
        self.ttl = ttl
        self.key_prefix = key_prefix

    def get(self, key: str):
        """ Get a stored value

        Args:
            key (str): The key which is used for finding the results
        Returns:

        """
        return cache.get("{}{}".format(self.key_prefix, key))

    def get_keys(self, pattern: str):
        """ Returns a list of keys that matches the given pattern.

        Pattern uses * as wildcard. So use e.g. "*test" to find "123test"
        or "test*" to find "test123".

        Args:
            pattern (str): The pattern to look for
        Returns:
             keys (list): A list of found keys
        """
        return cache.keys(pattern)

    def set(self, key: str, val, use_ttl: bool = True):
        """ Set a key-value pair.

        With use_ttl one can decide whether the record shall be kept all the time or being dropped after time to live
        expires.

        Args:
            key (str): The key which is used for finding the results
            val: The value to be stored
            use_ttl:
        Returns:

        """
        if use_ttl:
            cache.set(
                "{}{}".format(self.key_prefix, key),
                val,
                timeout=self.ttl
            )
        else:
            cache.set(
                "{}{}".format(self.key_prefix, key),
                val,
            )

    def remove(self, key: str, use_internal_key_prefix: bool = False):
        """ Removes a record from the cache.

        Returns True if removing was successful, False otherwise

        Args:
            key (str): A key string
        Returns:
            success (bool): True|False
        """
        return cache.delete("{}{}".format(self.key_prefix if use_internal_key_prefix else "", key))


class DocumentCacher(SimpleCacher):
    def __init__(self, title: str, version: str, ttl: int = None):
        ttl = ttl or 60 * 30  # 30 minutes
        prefix = "document_{}_{}_".format(title, version)
        super().__init__(ttl, prefix)


class EPSGCacher(SimpleCacher):
    def __init__(self, ttl: int = None):
        ttl = ttl or 7 * 24 * 60 * 60  # 7 days
        prefix = "epsg_api_axis_order_"
        super().__init__(ttl, prefix)


class PreviewImageCacher(SimpleCacher):
    def __init__(self, ttl: int = None, metadata=None):
        ttl = ttl or 60 * 30  # 30 minutes
        prefix = "preview_{}_".format(metadata.id)
        self.crypto_handler = CryptoHandler()
        super().__init__(ttl, prefix)

    def set(self, params_dict: dict, img: dict, use_ttl: bool = True):
        """ Special setter for preview images.

        Takes a dict of parameter key-value pairs and an image as bytes and stores the image, using the hashed
        dict as key

        Args:
            params_dict (dict): The parameters
            img (dict): The preview image as bytes in a dict {"response": img(bytes), "content_type": img_mime_type}
            use_ttl:
        Returns:
             nothing
        """
        query_data_str = json.dumps(params_dict)
        _hash = self.crypto_handler.sha256(query_data_str)
        super().set(key=_hash, val=img, use_ttl=use_ttl)

    def get(self, params_dict: dict):
        """ Special getter for cached preview images.

        Takes a dict of parameter key-value pairs looks for the cached entry, using the hashed dict as key

        Args:
            params_dict (dict): The parameters
        Returns:
             nothing
        """
        query_data_str = json.dumps(params_dict)
        _hash = self.crypto_handler.sha256(query_data_str)
        return super().get(_hash)


class PageCacher(SimpleCacher):
    def __init__(self):
        super().__init__(-1, None)

    def remove_pages(self, key_like: str):
        """ Removes cached pages from the memory.

        Args:
            key_like (str): A string that occurs in the searched key
        Returns:

        """
        keys = self.get_keys("*" + key_like + "*")
        for key in keys:
            self.remove(key)
