import { notification, Select } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';


export interface OptionData {
  key: string | number;
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
  const [listOperation, { loading, error, response }] = useOperationMethod('list'+resourceType);

  useEffect(() => {
    if (!response){
      // force initial options
      listOperation();
    }
    const newOptions: OptionData[] = [] ;
    if (response?.data.data) {
      for (const obj of response.data.data) {
        newOptions.push({ 
          key: obj.id,
          value: obj.id, 
          label: obj.attributes.stringRepresentation, 
          attributes: obj.attributes, 
          relationships: obj.relationships });
      }
    }
    setOptions(newOptions);
  }, [listOperation, response]);

  useEffect(() => {
    if (error) {
      notification.error({ 
        message: `Something went wrong while trying to get data for field ${fieldSchema.title}`, 
        description: `used OperationId: ${'list'+resourceType} ${error.message}`,
        duration: 10 
      });
    }
  }, [error, fieldSchema.title, resourceType]);
      
  function onSearch(value: any) {
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
        showSearch={true}
        allowClear={true}
        placeholder={'select '+fieldSchema.title || 'select'}
        //autoClearSearchValue={true}
        onSearch={onSearch}
        options={options}
        loading={loading}
        filterOption={false}
        
        {...passThroughProps}
      />
    </>
  );
};
    
export default RepoSelect;
