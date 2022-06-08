import SchemaSelect from '@/components/SchemaSelect';
import type {
  JsonApiErrorObject,
  JsonApiPrimaryData,
  ResourceIdentifierObject,
} from '@/utils/jsonapi';
import { buildJsonApiPayload } from '@/utils/jsonapi';
import type { ProFieldValueType } from '@ant-design/pro-field';
import type { ProFormColumnsType } from '@ant-design/pro-form';
import { BetaSchemaForm } from '@ant-design/pro-form';
import type { FormSchema } from '@ant-design/pro-form/lib/components/SchemaForm';
import { notification } from 'antd';
import type { FormInstance } from 'antd/lib/form/Form';
import { useForm } from 'antd/lib/form/Form';
import type { AxiosError, AxiosResponse } from 'openapi-client-axios';
import type { OpenAPIV3 } from 'openapi-types';
import type { ReactElement } from 'react';
import { useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useIntl } from 'umi';

export type SchemaFormProps = {
  resourceType: string;
  resourceId?: string | number;
  onSuccess?: { (response: AxiosResponse, created: boolean): void } | null;
} & Omit<Omit<FormSchema, 'columns'>, 'layoutType'>; // TODO why does ts freak out when we do not omit 'layoutType' here?

function getValueType(fieldSchema: any): ProFieldValueType {
  if (fieldSchema.type === 'string') {
    if (fieldSchema.format === 'date-time') {
      return 'dateTime';
    }
  } else if (fieldSchema.type === 'boolean') {
    return 'switch';
  }
  return 'text';
}

function getFormItemProps(fieldSchema: any, isRequired = false): any {
  const rules: any[] = [];

  if (isRequired) {
    rules.push({ required: true });
  }

  if (fieldSchema.minimum) {
    rules.push({ min: fieldSchema.minimum });
  }

  if (fieldSchema.maximum) {
    rules.push({ max: fieldSchema.maximum });
  }

  switch (fieldSchema.format) {
    case 'uri':
      rules.push({ type: 'url' });
      break;
    case 'boolean':
      rules.push({ type: 'boolean' });
  }

  return {
    extra: fieldSchema.description,
    rules: rules,
  };
}

function augmentColumns(resourceSchema: any): ProFormColumnsType[] {
  const columns: ProFormColumnsType[] = [];
  const requiredResourceProperties = resourceSchema.attributes?.required;
  const resourceProperties = resourceSchema.attributes?.properties;

  const requiredRelatedResources = resourceSchema.relationships?.required;
  const relatedResources = resourceSchema.relationships?.properties;

  for (const propName in resourceProperties) {
    const prop = resourceProperties[propName];
    const isRequired = requiredResourceProperties?.includes(propName) ? true : false;
    if (!prop.readOnly) {
      columns.push({
        title: prop.title,
        dataIndex: propName,
        initialValue: prop.default ? prop.default : undefined,
        //readonly: prop.readOnly ? prop.readOnly : false,
        valueType: getValueType(prop),
        formItemProps: getFormItemProps(prop, isRequired),
      });
    }
  }

  for (const relationName in relatedResources) {
    const relation = relatedResources[relationName];
    const isRequired = requiredRelatedResources?.includes(relationName) ? true : false;
    if (!relation.readOnly) {
      columns.push({
        title: relation.title,
        dataIndex: relationName,
        formItemProps: getFormItemProps(relation, isRequired),
        renderFormItem: () => (
          // TODO: pass in initialValues to RepoSelect component to fetch the string representations
          <SchemaSelect
            mode={relation.type === 'array' ? 'multiple' : undefined}
            resourceType={
              relation.type === 'array'
                ? relation.items.properties.type.enum[0]
                : relation.properties.type.enum[0]
            }
            fieldSchema={relation}
          />
        ),
      });
    }
  }
  return columns;
}

function getRequestSchema(operation: any): any {
  const requestBodyObject = operation?.requestBody as OpenAPIV3.RequestBodyObject;
  const schema = requestBodyObject?.content?.['application/vnd.api+json']
    .schema as OpenAPIV3.SchemaObject;
  const props = schema?.properties?.data as any;
  return props?.properties;
}

function setFormErrors(form: FormInstance, error: AxiosError) {
  const jsonApiErrors: JsonApiErrorObject[] = error?.response?.data?.errors;
  const fieldDatas: any[] = [];
  if (jsonApiErrors) {
    jsonApiErrors.forEach((jsonApiError) => {
      const fieldName = jsonApiError.source?.pointer?.split('/').pop();
      if (fieldName) {
        const exists = fieldDatas.some((fieldData) => {
          if (fieldData.name === fieldName) {
            fieldData.errors.push(jsonApiError.detail);
            return true;
          }
          return false;
        });
        if (!exists) {
          fieldDatas.push({ name: fieldName, errors: [jsonApiError.detail], help: undefined });
        }
      }
    });
    if (fieldDatas) {
      form.setFields(fieldDatas);
    }
  }
}

const SchemaForm = ({
  resourceType,
  resourceId = '',
  onSuccess = null,
  ...passThroughProps
}: SchemaFormProps): ReactElement => {
  const intl = useIntl();
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const operationId = resourceId ? 'update' + resourceType : 'add' + resourceType;

  const [
    remoteOperation,
    { response: remoteOperationResponse, error: remoteOperationError, api: remoteOperationApi },
  ] = useOperationMethod(operationId);

  const [getRemoteResource, { response: resourceResponse }] = useOperationMethod(
    'get' + resourceType,
  );

  const [columns, setColumns] = useState<ProFormColumnsType[]>([]);
  const [description, setDescription] = useState<string>(operationId);

  const _resourceId = useRef(resourceId);

  const [form] = useForm(passThroughProps.form);

  useEffect(() => {
    if (resourceId) {
      getRemoteResource(resourceId);
    }
  }, [getRemoteResource, resourceId]);

  useEffect(() => {
    if (resourceResponse) {
      const initialValues: any = {};
      const resource: JsonApiPrimaryData = resourceResponse.data.data;
      for (const key in resource.attributes) {
        initialValues[key] = resource.attributes[key];
      }
      for (const key in resource.relationships) {
        const relations = resource.relationships[key];
        if (Array.isArray(relations.data)) {
          const relatedIds: any[] = [];
          relations.data.forEach((relation: any) => {
            relatedIds.push(relation.id);
          });
          initialValues[key] = relatedIds;
        } else {
          initialValues[key] = relations?.data?.id;
        }
      }
      form.setFieldsValue(initialValues);
    }
  }, [resourceResponse, form]);

  /**
   * @description Hook to run on error response from the remote server
   */
  useEffect(() => {
    const axiosError = remoteOperationError as AxiosError;
    if (axiosError && axiosError?.response?.status !== 400 && mounted.current) {
      notification.error({
        message: 'Something went wrong while trying to send data',
        description: `used OperationId: ${operationId} ${axiosError.message}`,
        duration: 10,
      });
    }
    if (axiosError?.response?.status === 400) {
      setFormErrors(form, axiosError);
    }
  }, [remoteOperationError, form, operationId]);

  /**
   * @description Hook to run on success response from the remote server
   */
  useEffect(() => {
    // TODO: this hook is rendering to often... fix it!
    if (remoteOperationResponse && mounted.current) {
      let message = 'unknown';
      switch (remoteOperationResponse.status) {
        case 200:
          message = intl.formatMessage(
            { id: 'component.schemaForm.updateSuccessful' },
            { resource: remoteOperationResponse.data?.data?.attributes?.stringRepresentation },
          );
          break;
        case 201:
          message = intl.formatMessage(
            { id: 'component.schemaForm.createSuccessful' },
            { resource: remoteOperationResponse.data?.data?.attributes?.stringRepresentation },
          );
          break;
        case 202:
          message = intl.formatMessage(
            { id: 'component.schemaForm.backgroundCreationStarted' },
            { resourceType: remoteOperationResponse.data?.data?.type },
          );
          break;
      }
      notification.success({
        message: message,
      });
      if (onSuccess) {
        onSuccess(remoteOperationResponse, _resourceId.current ? false : true);
      }
    }
    // TODO check invocations of SchemaForm and use useCallback
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remoteOperationResponse, _resourceId]);

  /**
   * @description Hook to initial pro form with argumentColumns
   */
  useEffect(() => {
    const operation = remoteOperationApi.getOperation(operationId);
    const requestSchema = getRequestSchema(operation);
    setDescription(operation?.description || operationId);

    if (requestSchema) {
      setColumns(augmentColumns(requestSchema));
    }
  }, [remoteOperationApi, operationId]);

  async function onFinish(formData: any): Promise<boolean> {
    const operation = remoteOperationApi.getOperation(operationId);
    const requestSchema = getRequestSchema(operation);
    const attributes: any = {};
    const relationships: any = {};

    for (const field in formData) {
      const isAttribute = Object.prototype.hasOwnProperty.call(
        requestSchema?.attributes?.properties,
        field,
      );
      const isRelationship =
        !isAttribute &&
        Object.prototype.hasOwnProperty.call(requestSchema?.relationships?.properties, field);
      if (isAttribute) {
        attributes[field] = formData[field];
      }
      if (isRelationship) {
        let relationData: any;
        if (requestSchema?.relationships?.properties[field].type === 'array') {
          relationData = [] as ResourceIdentifierObject[];
          formData[field].forEach((id: string | number) => {
            // eslint-disable-next-line max-len
            relationData.push({
              type: requestSchema.relationships.properties[field].items.properties.type.enum[0],
              id: id,
            });
          });
        } else {
          relationData = {
            type: requestSchema.relationships.properties[field].properties.type.enum[0],
            id: formData[field],
          } as ResourceIdentifierObject;
        }
        if (formData[field]) {
          relationships[field] = { data: relationData };
        }
      }
    }

    const payload = buildJsonApiPayload(
      requestSchema.type.enum[0],
      resourceId,
      attributes,
      relationships,
    );
    if (resourceId) {
      remoteOperation(resourceId, payload);
    } else {
      remoteOperation({}, payload);
    }

    return true;
  }

  return (
    <>
      <BetaSchemaForm
        {...passThroughProps}
        columns={columns}
        description={description}
        onFinish={onFinish}
        form={form}
      />
    </>
  );
};

export default SchemaForm;
