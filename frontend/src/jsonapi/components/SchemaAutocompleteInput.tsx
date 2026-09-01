import { type ReactElement, useCallback, useMemo, useState } from 'react';
import { AutocompleteArrayInput, AutocompleteArrayInputProps, AutocompleteInput, GetListParams, Identifier, type RaRecord, useGetList, useGetMany, useRecordContext } from 'react-admin';
import { useWatch } from 'react-hook-form';
import { RelatedResource } from '../../providers/dataProvider';
import useSchemaRecordRepresentation from '../hooks/useSchemaRecordRepresentation';


export interface SchemaAutocompleteInputProps extends AutocompleteArrayInputProps {
  reference: string
  relatedResource?: RelatedResource
  source: string
  params?: GetListParams
  getListParams?: GetListParams
  initialFilter?: any
}


/**
 * DataRequest Workflow:
 * 1. check if record has initial data
 * 2. IF there are initial data, look for completed relation data ({id: 1, stringRepresentation: keyword, keyword: dop40} for example) inside the RaRecord which was collected by the json:api `include` query parameter in any component before
 * 3. IF there is no completed data, collect the information from remote api
 * 4. Fetch available choices on input search (with filter) and merge with the initial data (if any)
 * 5. Merge available choices and completed initial data
 */
const SchemaAutocompleteInput = (
  {
    reference,
    relatedResource,
    source,
    multiple,
    params,
    defaultValue,
    getListParams,
    initialFilter,
    ...rest
  }: SchemaAutocompleteInputProps
): ReactElement => {

  const [ filter, setFilter ] = useState<any>(initialFilter || {});
  const defaultParms = useMemo<GetListParams>(()=>{
    const _defaultParms: any = {
      sort: {field: '', order: 'DESC'}, 
      meta: {
        relatedResource: relatedResource,
        jsonApiParams: {}
      },
    }
    _defaultParms.meta.jsonApiParams[`fields[${reference}]`] = 'id,string_representation';
    return _defaultParms
  }, [reference, relatedResource])


  const optionText = useSchemaRecordRepresentation({resource: reference})

  const relatedRecord = useRecordContext(rest)
  const formValues: RaRecord | RaRecord[] = useWatch({name: source})

  const includedObjects = useMemo(() => {
    if (formValues === undefined) return []
    const valuesArray = Array.isArray(formValues) ? formValues : [formValues];
    return valuesArray.map((value: any) => {
        if (typeof value === 'object' && value.id && value.stringRepresentation) {
          return value; // already has completed data
        }
      }).filter((value: any) => value !== undefined)
    }
  , [formValues, relatedRecord, source])

  const missingObjects = useMemo(() => {
    if (formValues === undefined) return []
    const valuesArray = Array.isArray(formValues) ? formValues : [formValues];
    return valuesArray.filter(value => value.id && !includedObjects?.find(obj => obj.id === value.id))
  }, [])

  if (missingObjects && missingObjects.length > 0){
    console.warn(
      `No included objects found for ${source} in record ${relatedRecord?.id}.
      This may indicate that the related resource is not included in the API response. 
      Please check the API response and ensure that the related resource is included.
      Otherwise, the autocomplete input needs to fetch the data from the API, 
      which may result in additional requests and slower performance.`
    )
  }

  const { data: searchResults, isFetching: searchResultIsFetching, isLoading: searchResultIsLoading } = useGetList(
    reference, 
    {
      filter: filter, 
      ...defaultParms,
      ...getListParams, 
      ...params
    },
    {
      enabled: !!filter?.search, // only fetch when filter is set, which means the input is focused
    } 
  );

  const { data: getManyData, isFetching: isFetchingGetMany, isLoading: isloadingGetMany } = useGetMany(
    reference,
    {
      ids: missingObjects.map(value => value.id),
      ...defaultParms,
    },
    {
      enabled: missingObjects.length > 0, // only fetch when there are missing objects
    }
  );


  const mergedData = useMemo(() => {
    if (!formValues || !getManyData) return searchResults || [];

    const currentValuesArray = Array.isArray(formValues) ? formValues : [formValues];
    return currentValuesArray.map((value: any) => {
      if (typeof value === 'object' && value.id && value.stringRepresentation) {
        return value; // already has completed data
      }

      const matched = [...(getManyData || [])]?.find(
        (item: any) => item.id === (typeof value === 'object' ? value.id : value)
      );

      return matched || { id: typeof value === 'object' ? value.id : value }; // fallback to basic object if no match found
    });


  }, [searchResults, formValues, getManyData]);
 
  const choices = useMemo(() => [...mergedData, ...(searchResults||[])], [mergedData, searchResults]);

  const search = useCallback((searchText: string) => {
    setFilter((prev: any) => ({ ...prev, search: searchText }));
  }, [])

  // TODO: check if the resource has create endpoint; if so, we add an create component here
  if (multiple){
    return (
        <AutocompleteArrayInput 
          setFilter={(searchText: string) => search(searchText)}
          source={source}
          choices={choices}
          isLoading={searchResultIsLoading || isloadingGetMany}
          isFetching={searchResultIsFetching || isFetchingGetMany}
          optionText={optionText}
          parse={(value: Identifier[]) => { return value?.map(identifier => ({id: identifier})) }} // form input value (string) ---> parse ---> form state value
          format={(value: RaRecord[]) => value?.map(record => (record.id))}
          {...rest}
        />
      )
  } else {
    return (
      <AutocompleteInput
        setFilter={(searchText: string) => search(searchText)}
        source={source}
        choices={choices}
        isLoading={searchResultIsLoading || isloadingGetMany}
        isFetching={searchResultIsFetching || isFetchingGetMany}
        optionText={optionText}
        parse={(value: Identifier) => { return { id: value } }} // form input value (string) ---> parse ---> form state value
        format={(value: RaRecord) => value?.id}
        {...rest}
      />
    )
  }
}

export default SchemaAutocompleteInput
