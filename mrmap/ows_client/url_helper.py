"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""

from urllib import parse
from typing import List, Tuple


class UrlHelper:

    @staticmethod
    def build(url: str, queries: List[Tuple[str, str]]) -> str:
        """ Build url with provided queries.

        Adds queries to the url. If the url already contains the exact same query, its value will be replaced.

        Args:
            url (str): URL to which the params should be appended.
            queries (List[Tuple[str, str]]): List of tuples consisting of key value strings of queries.
        Returns:
            str: new url that contains additional queries.
        """
        _url = parse.urlparse(url)
        _queries = parse.parse_qs(_url.query)

        for query in queries:
            _queries[query[0]] = [str(query[1])]

        queries_strings = []
        for key, val in _queries.items():
            for v in val:
                q = '='.join([key, v])
                queries_strings.append(q)
        query_string = '&'.join(queries_strings)

        build = parse.urlunparse((_url.scheme, _url.netloc, _url.path, _url.params, query_string, _url.fragment))
        return build
