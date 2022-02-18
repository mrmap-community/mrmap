import { ProFieldValueType } from '@ant-design/pro-field';
import type { ProFormColumnsType } from '@ant-design/pro-form';
import { BetaSchemaForm } from '@ant-design/pro-form';
import { notification } from 'antd';
import { FormInstance, useForm } from 'antd/lib/form/Form';
import { AxiosError } from 'openapi-client-axios';
import { OpenAPIV3 } from 'openapi-types';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useNavigate } from 'react-router-dom';
import { JsonApiErrorObject } from '../../../Repos/JsonApiRepo';
import { buildJsonApiPayload } from '../../../Utils/JsonApiUtils';
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

function getFormItemProps(fieldSchema: any, isRequired = false): any {
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
    extra: fieldSchema.description,
    rules: rules
  };
}
    
function augmentColumns (
  resourceSchema: any): ProFormColumnsType[] {
  const columns: ProFormColumnsType[] = [];
  const requiredResourceProperties = resourceSchema.attributes?.required;
  const resourceProperties = resourceSchema.attributes?.properties;

  const requiredRelatedResources = resourceSchema.relationships?.required;
  const relatedResources = resourceSchema.relationships?.properties;

  for (const propName in resourceProperties) {
    const prop = resourceProperties[propName];
    const isRequired = requiredResourceProperties?.includes(propName) ? true : false;
    columns.push({
      title: prop.title,
      dataIndex: propName,
      initialValue: prop.default ? prop.default : undefined,
      readonly: prop.readOnly ? prop.readOnly : false,
      valueType: getValueType(prop),
      formItemProps: getFormItemProps(prop, isRequired)

    });
  }
  
  for (const relationName in relatedResources) {
    const relation = relatedResources[relationName];
    const isRequired = requiredRelatedResources?.includes(relationName) ? true : false;
    columns.push({
      title: relation.title,
      dataIndex: relationName,
      formItemProps: getFormItemProps(relation, isRequired),
      renderFormItem: () => 
        <RepoSelect 
          mode={relation.type === 'array' ? 'multiple' : undefined}
          resourceType={
            relation.type === 'array' ? relation.items.properties.type.enum[0] : relation.properties.type.enum[0]} 
          fieldSchema={relation} />
    });
    
  }
  return columns;
}

function getRequestSchema(operation: any): any{
  const requestBodyObject = operation?.requestBody as OpenAPIV3.RequestBodyObject;
  const schema = requestBodyObject?.content?.['application/vnd.api+json'].schema as OpenAPIV3.SchemaObject;
  const props = schema.properties?.data as any;
  return props.properties;
}

function setFormErrors(form: FormInstance, error: AxiosError) {
  const jsonApiErrors: JsonApiErrorObject[] = error?.response?.data?.errors;
  const fieldDatas: any[] = [];

  jsonApiErrors.forEach(jsonApiError => {
    const fieldName = jsonApiError.source?.pointer?.split('/').pop();
    if (fieldName){
      const exists = fieldDatas.some(fieldData => {
        if (fieldData.name === fieldName) {
          fieldData.errors.push(jsonApiError.detail);
          return true;
        }
        return false;
      });
      if (!exists){
        fieldDatas.push({ name: fieldName, errors: [jsonApiError.detail], help: undefined });
      }
    }
  });
  if (fieldDatas) {
    form.setFields(fieldDatas);
  }
}

const RepoForm = ({
  resourceType,
  resourceId = undefined,
  onSuccess = undefined,
  ...passThroughProps
}: any): ReactElement => {
  const operationId = resourceId ? 'update'+resourceType : 'add'+resourceType;
  const [remoteOperation, { response, error, api }] = useOperationMethod(operationId);
  const [columns, setColumns] = useState<ProFormColumnsType[]>([]);
  const [description, setDescription] = useState<string>(operationId);
  const [form] = useForm(passThroughProps.form);
  const navigate = useNavigate();


  useEffect(() => {
    const axiosError = error as AxiosError;
    if (axiosError && axiosError?.response?.status !== 400) {
      notification.error({ 
        message: 'Something went wrong while trying to send data', 
        description: `used OperationId: ${'list'+resourceType} ${axiosError.message}`,
        duration: 10 
      });
    }
    if (axiosError?.response?.status === 400){
      setFormErrors(form, axiosError);     
    }
  }, [error, form, resourceType]);

  useEffect(() => {
    if (response) {
      let message = 'unknown';
      switch(response.status){
      case 200:
        message = `Successfully updated ${response.data?.data?.attributes?.stringRepresentation}`;
        break;
      case 201:
        message = `Successfully created ${response.data?.data?.attributes?.stringRepresentation}`;
        break;
      case 202:
        message = `Successfully accepted creation job for resource ${resourceType}`;
        break;
      }
      notification.success({ 
        message: message, 
      });
      if (onSuccess){
        onSuccess();
      } else {
        navigate(-1);
      }
    }
  }, [resourceType, onSuccess, response, navigate]);

  useEffect(() => {
    const operation = api.getOperation(operationId);
    const requestSchema = getRequestSchema(operation);
    setDescription(operation?.description || operationId);

    if (requestSchema) {
      setColumns(augmentColumns(requestSchema));
    }
    
  }, [api, operationId]);     
  
  function onFinish(formData: any) {
    const operation = api.getOperation(operationId);
    const requestSchema = getRequestSchema(operation);
    const attributes : any = {};
    const relationships : any = {} ;

    for (const field in formData){
      const isAttribute = Object.prototype.hasOwnProperty.call(requestSchema?.attributes?.properties, field);
      const isRelationship = !isAttribute && 
      Object.prototype.hasOwnProperty.call(requestSchema?.relationships?.properties, field);
      if (isAttribute){   
        attributes[field] = formData[field];
      }
      if (isRelationship){
        if (requestSchema?.relationships?.properties[field].type === 'array'){
          // TODO
        } else {
          relationships[field] = { 
            'data': { 
              type: requestSchema.relationships.properties[field].properties.type.enum[0], 
              id: formData[field] 
            }
          };
        }
        
      }
    }
    const payload = buildJsonApiPayload(requestSchema.type.enum[0], attributes, relationships);
    return remoteOperation({}, payload);
  }

  return (
    <>
      <BetaSchemaForm
        columns={columns}
        description={description}
        onFinish={onFinish}
        form={form}
        {...passThroughProps}
      />
    </>
  );
};
  
export default RepoForm;
  
