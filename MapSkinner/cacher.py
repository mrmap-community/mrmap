"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 25.02.20

"""
from django.core.cache import cache


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

    def set(self, key: str, val: str, use_ttl: bool = True):
        """ Set a key-value pair.

        With use_ttl one can decide whether the record shall be kept all the time or being dropped after time to live
        expires.

        Args:
            key (str): The key which is used for finding the results
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

    def remove(self, key: str):
        """ Removes a record from the cache.

        Returns True if removing was successful, False otherwise

        Args:
            key (str): A key string
        Returns:
            success (bool): True|False
        """
        return cache.delete("{}{}".format(self.key_prefix, key))


class DocumentCacher(SimpleCacher):
    def __init__(self, title: str, version: str, ttl: int=None):
        ttl = ttl or 60 * 30  # 30 minutes
        prefix = "document_{}_{}_".format(title, version)
        super().__init__(ttl, prefix)

class EPSGCacher(SimpleCacher):
    def __init__(self, ttl: int=None):
        ttl = ttl or 7 * 24 * 60 * 60  # 7 days
        prefix = "epsg_api_axis_order_"
        super().__init__(ttl, prefix)