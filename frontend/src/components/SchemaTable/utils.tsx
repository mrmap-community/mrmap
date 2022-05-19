import type { JsonApiPrimaryData, ResourceLinkage } from '@/utils/jsonapi';
import { CheckCircleTwoTone, CloseCircleTwoTone, LinkOutlined } from '@ant-design/icons';
import type { ProColumnType } from '@ant-design/pro-table';
import { Badge, Button } from 'antd';
import Text from 'antd/lib/typography/Text';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import type { ReactNode } from 'react';
import type { ResourceTypes } from '.';

// required for parsing of German dates
dayjs.extend(customParseFormat);

export const buildSearchTransformDateRange = (dataIndex: string) => {
  return (values: any[]): Record<string, string> => {
    const queryParams: Record<string, string> = {};
    if (values[0]) {
      // re-parsing the date is not very nice, but as soon as we set a date format for the date picker
      // (via the column) the same (string) representation is used here in the transform function...
      queryParams[`filter[${dataIndex}.gte]`] = dayjs(values[0], 'DD.MM.YYYY')
        .startOf('day')
        .toISOString();
    }
    if (values[1]) {
      // TODO
      queryParams[`filter[${dataIndex}.lte]`] = dayjs(values[1], 'DD.MM.YYYY')
        .endOf('day')
        .toISOString();
    }
    return queryParams;
  };
};

export const buildSearchTransformText = (dataIndex: string, filterModifier?: string) => {
  return (value: string): Record<string, string> => {
    const queryParams: Record<string, string> = {};
    if (filterModifier) {
      queryParams[`filter[${dataIndex}.${filterModifier}]`] = value;
    } else {
      queryParams[`filter[${dataIndex}]`] = value;
    }
    return queryParams;
  };
};

export const renderEllipsis = (
  dataIndex: string,
  text: ReactNode,
  record: Record<string, unknown>,
): ReactNode => {
  const value = record[dataIndex];
  if (!value) {
    return '-';
  }
  if (typeof value !== 'string') {
    return typeof value;
  }
  return (
    <Text style={{ maxWidth: '200px' }} ellipsis={true}>
      {value}
    </Text>
  );
};

export const renderLink = (
  dataIndex: string,
  text: ReactNode,
  record: Record<string, string>,
): ReactNode => {
  const value = record[dataIndex];
  if (!value) {
    return '-';
  }
  return <a href={value}>Link</a>;
};

const augmentDateTimeColumn = (column: ProColumnType): ProColumnType => {
  const fieldProps = column.fieldProps || {};
  if (!fieldProps.format && !column.hideInTable) {
    // TODO i18n
    fieldProps.format = 'DD.MM.YYYY HH:mm:ss';
  }
  column.fieldProps = fieldProps;
  return column;
};

const mapOpenApiFilter = (column: ProColumnType, propSchema: any, queryParams: any) => {
  if (column.search && column.search.transform) {
    // manually defined mapping to query params
    return column;
  }
  if (column.valueType === 'option') {
    // value type does not support backend filtering
    return column;
  }
  if (column.hideInSearch) {
    // column hidden from search form anyway
    return column;
  }
  // try to derive mapping to query params automatically
  const name = column.dataIndex;

  if (column.valueType === 'text') {
    if (queryParams[`filter[${name}.icontains]`]) {
      column.search = {
        transform: buildSearchTransformText(`${name}`, 'icontains'),
      };
    }
  } else if (column.valueType === 'digit' || column.valueType === 'checkbox') {
    if (queryParams[`filter[${name}]`]) {
      column.search = {
        transform: buildSearchTransformText(`${name}`),
      };
    }
  } else if (column.valueType === undefined) {
    column.search = {
      transform: buildSearchTransformText(`${name}`),
    };
  }

  return column;
};

export const mapOpenApiSchemaToProTableColumn = (
  proColumn: ProColumnType,
  propSchema: { type: string; format: string; title: string },
  queryParams: any,
  onRelationButtonClick: (relatedDefinition: ResourceTypes) => void,
): ProColumnType => {
  let column = proColumn;
  column.title = column.title || propSchema.title || column.dataIndex;
  const paramName = column.dataIndex as string;

  // https://procomponents.ant.design/components/schema#valuetype
  if (!column.valueType) {
    if (propSchema.type === 'string') {
      switch (propSchema.format) {
        case 'date-time':
          column.valueType = 'dateTime';
          column = augmentDateTimeColumn(column);
          break;
        case 'uri':
          column.render = renderLink.bind(null, column.dataIndex as string) as any;
          column.valueType = 'text';
          break;
        case 'uuid':
        case 'binary':
          column.valueType = 'text';
          break;
        case 'geojson':
          // TODO: here should be a map component
          column.valueType = 'textarea';
          break;
        default:
          column.render = renderEllipsis.bind(null, column.dataIndex as string) as any;
          column.valueType = 'text';
          break;
      }
    } else if (propSchema.type === 'integer') {
      column.valueType = 'digit';
    } else if (propSchema.type === 'number') {
      column.valueType = 'digit';
    } else if (propSchema.type === 'boolean') {
      column.valueType = 'checkbox';
      column.valueEnum = { true: { text: column.title } };
      column.formItemProps = { label: '' };
      column.renderText = (text) => {
        return text ? (
          <CheckCircleTwoTone twoToneColor="#52c41a" />
        ) : (
          <CloseCircleTwoTone twoToneColor="#eb2f96" />
        );
      };
    } else if (propSchema.type === 'object'){
      // multiple relation field (m2n)
      column.valueType = 'textarea';
      column.renderText = (relationshipObject, proTableRecord) => {
        // const _record = record as JsonApiPrimaryData;
        // if (column?.dataIndex){
        //   const index = column.dataIndex as string;
        //   const jsonApiRelation = _record.relationships?.[index];
        //   return jsonApiRelation.data ? 1 : '-'
        // }
        return '-'
      }
    } else if (propSchema.type === 'array'){
      // singe relation field (o2o)
      column.valueType = 'textarea';
      column.renderText = (relationshipObject: ResourceLinkage, proTableRecord: any) => {
        const _proTableRecord = proTableRecord._jsonApiPrimaryData as JsonApiPrimaryData;
        console.log(_proTableRecord);
        const relatedDefinition: ResourceTypes = {
          baseResourceType: relationshipObject?.data?.[0]?.type,
          nestedResource: {
            id: _proTableRecord.id,
            type: _proTableRecord.type
          }
        };
        return (
        <Badge size='small' count={relationshipObject?.meta?.count}>
          <Button disabled={relationshipObject?.meta?.count === 0 ? true : false} size='small' icon={<LinkOutlined />} onClick={() => {onRelationButtonClick(relatedDefinition)}}/>
        </Badge>)
      }
    }
    // @ts-ignore
    // column.ellipsis = {
    //   showTitle: true,
    // };
  }
  const sortableColumns: string[] = queryParams.sort?.schema?.enum;
  if (sortableColumns?.includes(paramName)) {
    column.sorter = true;
  } else {
    column.sorter = false;
  }

  mapOpenApiFilter(column, propSchema, queryParams);
  if ((!column.search || !column.search.transform) && column.valueType !== 'option') {
    column.search = false;
  }

  return column;
};

/**
 * @description Transforms the given JsonApiPrimayData to a flat object which can be used by the antd pro table
 * @param data 
 * @returns 
 */
export const transformJsonApiPrimaryDataToRow = (data: JsonApiPrimaryData) => {
  return {
    key: data.id,
    id: data.id,
    ...data.attributes,
    ...data.relationships,
    _jsonApiPrimaryData: data
  };
};