import { ProColumnType } from '@ant-design/pro-table';
import Text from 'antd/lib/typography/Text';
import React, { ReactNode } from 'react';

export const renderEllipsis = (dataIndex: string, text: ReactNode, record: any): ReactNode => {
  const value = record[dataIndex];
  if (!value) {
    return '-';
  }
  if (typeof (value) !== 'string') {
    return typeof (value);
  }
  return (<Text style={{ maxWidth: '200px' }} ellipsis={true}>{value}</Text>);
};

export const renderLink = (dataIndex: string, text: ReactNode, record: any): ReactNode => {
  const value = record[dataIndex];
  if (!value) {
    return '-';
  }
  return <a href={value}>Link</a>;
};

export const augmentColumnWithJsonSchema = (column: ProColumnType, propSchema: any) : ProColumnType => {
  column.title = column.title || column.dataIndex;

  // https://procomponents.ant.design/components/schema#valuetype
  if (!column.valueType) {
    if (propSchema.type === 'string') {
      if (propSchema.format === 'date-time') {
        column.valueType = 'dateTime';
      } else if (propSchema.format === 'uri') {
        column.render = renderLink.bind(null, column.dataIndex as string) as any;
      } else if (propSchema.format === 'uuid') {
        // column.render = renderLink.bind(null, column.dataIndex as string) as any;
      } else if (propSchema.format === 'binary') {
        // column.render = renderLink.bind(null, column.dataIndex as string) as any;
      } else {
        console.log('****', propSchema.format);
        column.render = renderEllipsis.bind(null, column.dataIndex as string) as any;
      }
    } else if (propSchema.type === 'integer') {
      column.valueType = 'digit';
    }
  }

  if (column.valueType === 'dateTime') {
    column = augmentDateTimeColumn(column);
  }

  return column;
};

const augmentDateTimeColumn = (column: ProColumnType) : ProColumnType => {
  const fieldProps = column.fieldProps || {};
  if (!fieldProps.format) {
    // TODO i18n
    fieldProps.format = 'DD.MM.YYYY HH:mm:ss';
  }
  column.fieldProps = fieldProps;
  return column;
};
