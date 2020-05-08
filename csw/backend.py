"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from django.db.models import QuerySet, Q
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
        self.queryables = {}

        for tname in self.context.model['typenames']:
            for qname in self.context.model['typenames'][tname]['queryables']:
                self.queryables[qname] = {}
                items = list(self.context.model['typenames'][tname]['queryables'][qname].items())

                for qkey, qvalue in items:
                    self.queryables[qname][qkey] = qvalue

        # flatten all queryables
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
            identifier__in=ids,
            is_active=True
        )
        return list(metadatas)

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

        mocked_property_columns = [
            "csw_keywords",
            "csw_typename",
            "csw_schema",
            "csw_anytext",
            "csw_bounding_geometry",
            "csw_srs",
            "csw_organizationname",
            "csw_category",
            "csw_temp_dim_start",
            "csw_temp_dim_end",
            "csw_service_type",
            "csw_service_version",
        ]

        # Prefilter using constraint parameter
        if constraint:
            if "where" in constraint:
                found_mocked_column = {mock: mock in constraint["where"] for mock in mocked_property_columns}
                if True in found_mocked_column.values():
                    all_md = self._resolve_mocked_property_columns(constraint["values"], all_md, found_mocked_column)
                else:
                    all_md = all_md.extra(where=[constraint["where"]], params=constraint["values"])
            else:
                # ToDo?
                pass

        # Sort queryset
        if isinstance(sortby, dict):
            # Specification declares that each item follows the format 'attrib_name:A|D' where A indicates ASC
            # and D indicates DESC
            attrib = sortby["propertyname"]
            desc = sortby["order"].upper() == "DESC"
            # Convert A and D to '' and '-' which is used in Django's order_by() syntax
            if desc:
                attrib = "-" + attrib
            all_md = all_md.order_by(attrib)

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

    def _filter_mockup_csw_keywords(self, metadatas: QuerySet, values: list):
        q = Q()
        for query_elem in values:
            q |= Q(keywords__keyword__icontains=query_elem)

        metadatas = metadatas.filter(q)
        return metadatas

    def _resolve_mocked_property_columns(self, values: list, metadatas: QuerySet, found_mocked_columns: dict):
        """ Dynamically calls specialized filter functions for mocked property columns.

        There are propertys of Metadata which are not real class attributes but rather wrapped complex requests to nested
        attributes, disguised using @property as class attributes.
        This is needed to work with pycsw mapping style found in mappings.py

        There have to be filter functions for each mocked csw_PROP which can not be resolved directly into a table column.

        Args:
            values (list): The requested values to filter for
            metadatas (QuerySet): The metadata queryset
            found_mocked_columns (dict): A dict containing which mocked property is requested
        Returns:
             metadatas (QuerySet): The filtered queryset
        """
        # Clean values strings
        values = [v.replace("%", "") for v in values]

        # Get only the csw_PROP names which shall be filtered for
        filter_for = [key for key, val in found_mocked_columns.items() if val is True]

        # Call dynamically the matching filter function
        for filter_property in filter_for:
            filter_function = "_filter_mockup_{}".format(filter_property)
            metadatas = getattr(self, filter_function)(metadatas, values)

        return metadatas
