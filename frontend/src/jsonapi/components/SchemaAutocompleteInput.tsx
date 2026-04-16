import { type ReactElement, useCallback, useMemo, useState } from 'react';
import { AutocompleteArrayInput, AutocompleteArrayInputProps, AutocompleteInput, GetListParams, Identifier, type RaRecord, useGetList, useRecordContext } from 'react-admin';

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
 * 4. Fetch available choices on input focus
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
  const [ filter, setFilter] = useState<any>(initialFilter || {});
  const contextRecord = useRecordContext(rest)
  const currentValues = useMemo(() => (contextRecord?.[source]), [contextRecord, source])

  const defaultParms = useMemo<GetListParams>(()=>{
    const _defaultParms: any = {
      filter: filter, 
      sort: {field: '', order: 'DESC'}, 
      meta: {
        relatedResource: relatedResource,
        jsonApiParams: {}
      },
      ...params
    }
    _defaultParms.meta.jsonApiParams[`fields[${reference}]`] = 'id,string_representation';
    return _defaultParms
  }, [filter])

  const { data, isFetching } = useGetList(
    reference, 
    {
      ...defaultParms,
      ...getListParams
    },
    {
      // FIXME: only fetch if the user types >1 characters
      enabled: filter?.search !== undefined, // only fetch when filter is set, which means the input is focused
    } 
  );

  const mergedData = useMemo(() => {
    if (!currentValues) return data || [];
    const currentValuesArray = Array.isArray(currentValues) ? currentValues : [currentValues];
    const completedCurrentValues = currentValuesArray.map((value: any) => {
      if (typeof value === 'object' && value.id && value.string_representation) {
        return value; // already has completed data
      }
      const matched = data?.find((item: any) => item.id === (typeof value === 'object' ? value.id : value));
      return matched || { id: typeof value === 'object' ? value.id : value }; // fallback to basic object if no match found
    });
    const merged = [...(data || []), ...completedCurrentValues.filter((cv: any) => !data?.some((d: any) => d.id === cv.id))];
    return merged;
  }, [data, currentValues]);
 
  const search = useCallback((searchText: string) => {
    setFilter((prev: any) => ({ ...prev, search: searchText }));
  }, [])

  const optionText = useSchemaRecordRepresentation({resource: reference})
  console.log(rest)
  // TODO: check if the resource has create endpoint; if so, we add an create component here
  if (multiple){
    return (
        <AutocompleteArrayInput 
          setFilter={(searchText: string) => search(searchText)}
          onOpen={() => search(filter.search || '')}
          source={source}
          choices={mergedData}
          isFetching={isFetching}
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
        onOpen={() => search(filter.search || '')}
        source={source}
        choices={mergedData}
        isFetching={isFetching}
        optionText={optionText}
        parse={(value: Identifier) => { return { id: value } }} // form input value (string) ---> parse ---> form state value
        format={(value: RaRecord) => value?.id}
        {...rest}

      />
    )
  }
}

export default SchemaAutocompleteInput
