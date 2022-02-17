import { notification, Select } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';


export interface OptionData {
  value: string | number;
  label: string;
  attributes?: any;
  relationships?: any;
}

const RepoSelect = ({
  resourceType,
  fieldSchema,
  ...passThroughProps
}: any): ReactElement => {

  const [options, setOptions] = useState<OptionData[]>([]);
  const [listOperation, { loading, error, response, api }] = useOperationMethod('list'+resourceType);
  
  useEffect(() => {
    const newOptions: OptionData[] = [] ;
    if (response?.data.data) {
      for (const obj of response.data.data) {

        newOptions.push({ 
          value: obj.id, 
          label: obj.attributes.stringRepresentation, 
          attributes: obj.attributes, 
          relationships: obj.relationships });
      }
    }
    setOptions(newOptions);
  }, [response]);

  useEffect(() => {
    if (error) {
      notification.error({ message: 'Something went wrong.' });
    }
  }, [error]);

  function onChange(value: any) {
    console.log(`changed ${value}`);
  }

  function onSelect(value: any) {
    console.log(`selected  ${value}`);
  }
      
  function onSearch(value: any) {
    console.log('search:', value);
    // TODO: currently there is a bug in backend django 
    // json:api package, where sparse fields from query param are not used as configured
    const params = [
      { name: 'filter[search]', value: value, in: 'query' },
      { name: 'fields['+resourceType+']', value: 'id,string_representation', in: 'query' }
    ];
    listOperation(params);
  }
    
  return (
    <>

      <Select
        showSearch
        allowClear={true}
        placeholder={'select '+fieldSchema.title || 'select'}
        autoClearSearchValue={true}

        //optionFilterProp='children'
        onChange={onChange}
        onSearch={onSearch}
        onSelect={onSelect}
        options={options}
        loading={loading}
        filterOption={false}
        
        {...passThroughProps}
      />
     
    </>
  );
};
    
export default RepoSelect;
