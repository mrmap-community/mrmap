"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from pycsw.core.repository import Repository

from MapSkinner import settings
from service.models import Metadata


class CswCustomRepository(Repository):
    """ Custom backend to handle CSW requests using pycsw

    """
    def __init__(self, context, repo_filter=None):
        self.context = context
        self.filter = repo_filter
        self.fts = False
        self.label = 'MrMapCSW'
        self.local_ingest = True
        self.queryables = {
        }

        for tname in self.context.model['typenames']:
            for qname in self.context.model['typenames'][tname]['queryables']:
                self.queryables[qname] = {}
                items = list(self.context.model['typenames'][tname]['queryables'][qname].items())

                for qkey, qvalue in items:
                    self.queryables[qname][qkey] = qvalue

        # flatten all queryables
        # TODO smarter way of doing this
        self.queryables['_all'] = {}
        for qbl in self.queryables:
            self.queryables['_all'].update(self.queryables[qbl])
        self.queryables['_all'].update(self.context.md_core_model['mappings'])

        self.dbtype = settings.DATABASES['default']['ENGINE'].split('.')[-1]

        if self.dbtype == 'postgis':
            self.dbtype = 'postgresql+postgis+wkt'

    def query_ids(self, ids):
        """ Implementation of GetRecordById operation

        Args:
            ids (list): List of identifiers
        Returns:
             list: number of results, results
        """
        metadatas = Metadata.objects.filter(
            identifier__in=ids
        )
        result_count_str = str(metadatas.count())
        return [result_count_str, list(metadatas)]

    def query(self, constraint, sortby=None, typenames=None, maxrecords=10, startposition=0):
        """ Implementation of GetRecords operation

        Args:
            constraint (str): Additional CSW constraints
            sortby (str): Identifies attribute which is used for sorting
            typenames (str): Specifies the type of the response (gmd:MD_Metadata, ...)
            maxrecords (int): The amount of records returned in one call
            startposition (int): The start position of the returned records
        Returns:
             list: number of results, results
        """
        all_md = Metadata.objects.filter(
            is_active=True
        )

        # Sort queryset
        if isinstance(sortby, list):
            order_by_list = []
            for sort_item in sortby:
                # Specification declares that each item follows the format 'attrib_name:A|D' where A indicates ASC
                # and D indicates DESC
                sort_item_splitted = sort_item.split(":")
                attrib = sort_item_splitted[0]
                asc = sort_item_splitted[1].upper() == "A"

                # Convert A and D to '' and '-' which is used in Django's order_by() syntax
                if asc:
                    attrib = "-" + attrib
                order_by_list.append(attrib)
            all_md.order_by(order_by_list)

        result_count_str = str(all_md.count())
        results = all_md[int(startposition):int(startposition) + int(maxrecords)]
        return [result_count_str, list(results)]

    def query_domain(self, domain, typenames, domainquerytype='list',
        count=False):
        # ToDo: Not implemented yet
        pass

    def update(self, record=None, recprops=None, constraint=None):
        # Not to be supported
        pass

    def delete(self, constraint):
        # Not to be supported
        pass
