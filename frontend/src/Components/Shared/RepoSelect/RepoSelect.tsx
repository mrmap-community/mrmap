import { Select } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';


const { Option } = Select;




const RepoSelect = ({
  resourceType,
  ...passThroughProps
}: any): ReactElement => {
    
  const [options, setOptions] = useState<any[]>([]);
  const [listOperation, { loading, error, response, api }] = useOperationMethod('list'+resourceType);

  useEffect(() => {
    const newOptions = [];
    if (response?.data.data) {
      for (const obj of response.data.data) {

        newOptions.push({ id: obj.id, value: obj.attributes.stringRepresentation });
      }
    }
    setOptions(newOptions);
  }, [response]);

  function onChange(value: any) {
    console.log(`selected ${value}`);
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
        placeholder='Select a person'
        optionFilterProp='children'
        onChange={onChange}
        onSearch={onSearch}
        options={options}
        filterOption={(input, option) =>
          option?.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
        }
        {...passThroughProps}
      />
    </>
  );
};
    
export default RepoSelect;
