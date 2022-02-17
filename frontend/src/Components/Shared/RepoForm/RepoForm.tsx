import { ProFieldValueType } from '@ant-design/pro-field';
import type { ProFormColumnsType } from '@ant-design/pro-form';
import { BetaSchemaForm } from '@ant-design/pro-form';
import { OpenAPIV3 } from 'openapi-types';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import RepoSelect from '../RepoSelect/RepoSelect';

function getValueType(fieldSchema: any):  ProFieldValueType {
  if (fieldSchema.type === 'string') {
    if (fieldSchema.format === 'date-time'){
      return 'dateTime';
    }
  } else if (fieldSchema.type ==='boolean') {
    return 'switch';
  } 
  return 'text';   
}

function getFieldProps(fieldSchema: any): any {
  return {
    placeholder: fieldSchema.description ? fieldSchema.description: undefined,
  };
}

function getFormItemProps(fieldSchema: any, isRequired = true): any {
  const rules = [];

  if (isRequired){
    rules.push({ required: true });
  }
  
  if (fieldSchema.minimum) {
    rules.push({ min: fieldSchema.minimum });
  }

  if (fieldSchema.maximum) {
    rules.push({ max: fieldSchema.maximum });
  }

  switch (fieldSchema.format){
  case 'uri':
    rules.push({ type: 'url' });
    break;
  case 'boolean':
    rules.push({ type: 'boolean' });
  }
  
  return {
    rules: rules
  };
}
    
function augmentColumns (
  resourceSchema: any): ProFormColumnsType[] {
    
  const columns: ProFormColumnsType[] = [];
  const requiredResourceProperties = resourceSchema.properties?.data?.properties?.attributes?.required;
  const resourceProperties = resourceSchema.properties?.data?.properties?.attributes?.properties;

  const requiredRelatedResources = resourceSchema.properties?.data?.properties?.relationships?.required;
  const relatedResources = resourceSchema.properties?.data?.properties?.relationships?.properties;

  for (const propName in resourceProperties) {
    const prop = resourceProperties[propName];
    const isRequired = true ? requiredResourceProperties?.includes(propName) : false;
    
    const column: ProFormColumnsType = {
      title: prop.title,
      dataIndex: propName,
      initialValue: prop.default ? prop.default : undefined,
      readonly: prop.readOnly ? prop.readOnly : false,
      valueType: getValueType(prop),
      fieldProps: getFieldProps(prop),
      formItemProps: getFormItemProps(prop, isRequired)
    };
    columns.push(column);
  }
  
  for (const relationName in relatedResources) {
    const relation = relatedResources[relationName];

    if (relation.type === 'array'){
      // we need a multiselect
      const relatedResourceType = relation.items.properties.type.enum[0];
      const column: ProFormColumnsType = {
        title: relation.title,
        dataIndex: relation.relationName,
        valueType: 'text'
        //renderFormItem: () => {};
      };
      columns.push(column);
    } else {
      // we need a select
      const relatedResourceType = relation.properties.type.enum[0];
      const column: ProFormColumnsType = {
        title: relation.title,
        dataIndex: relation.relationName,
        valueType: 'text',
        renderFormItem: () => <RepoSelect resourceType={relatedResourceType} fieldSchema={relation}/>
      };
      columns.push(column);
    }
  }

  return columns;
}


const RepoForm = ({
  resourceType,
  resourceId = undefined,
  ...passThroughProps
}: any): ReactElement => {
  
  const operationId = resourceId ? 'update'+resourceType : 'add'+resourceType;
  const [remoteOperation, { loading, error, response, api }] = useOperationMethod(operationId);
  const [columns, setColumns] = useState<ProFormColumnsType[]>([]);
  const [description, setDescription] = useState<string>(operationId);

  useEffect(() => {
    const operation = api.getOperation(operationId);
    const requestBodyObject = operation?.requestBody as OpenAPIV3.RequestBodyObject;
    const requestSchema = requestBodyObject?.content?.['application/vnd.api+json'].schema;

    setDescription(operation?.description || operationId);

    if (requestSchema) {
      setColumns(augmentColumns(requestSchema));
    }
    
  }, [api, operationId]);     

  
  return (
    <>
      <BetaSchemaForm
        columns={columns}
        description={description}
        layoutType='Form'
        onFinish={async (values) => {
          // TODO: post data with the remoteOperation function
          console.log(values);
        }}
        {...passThroughProps}
      />
    </>
  );
};
  
export default RepoForm;
  
