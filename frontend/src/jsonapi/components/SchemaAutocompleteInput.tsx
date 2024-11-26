import { type ReactElement, useState } from 'react';
import { AutocompleteArrayInput, AutocompleteArrayInputProps, AutocompleteInput, GetListParams, Identifier, type RaRecord, useGetList } from 'react-admin';

import useSchemaRecordRepresentation from '../hooks/useSchemaRecordRepresentation';
export interface SchemaAutocompleteInputProps extends AutocompleteArrayInputProps {
  reference: string
  source: string
  params?: GetListParams
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
    source,
    multiple,
    params,
    defaultValue,
    ...rest
  }: SchemaAutocompleteInputProps
): ReactElement => {
  const [ filter, setFilter] = useState<any>();
  
  const { data, isPending, isFetching } = useGetList(reference, {filter: filter, sort: {field: '', order: 'DESC'}, ...params});

  const optionText = useSchemaRecordRepresentation({resource: reference})


  if (multiple){
    return (
        <AutocompleteArrayInput 
          setFilter={(searchText: string) => setFilter({ search: searchText})}
          source={source}
          choices={data}
          isPending={isPending}
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
        setFilter={(searchText: string) => setFilter({ search: searchText})}
        source={source}
        choices={data}
        isPending={isPending}
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
