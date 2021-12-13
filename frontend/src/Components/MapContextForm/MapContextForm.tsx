import { InfoCircleOutlined } from '@ant-design/icons';
import { Form } from 'antd';
import React, { FC } from 'react';

import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';

interface MapContextFormProps {
  form?: any;
  onSubmit?:(values: any)=>void;
}

export const MapContextForm: FC<MapContextFormProps> = ({
  form = undefined,
  onSubmit = () => undefined
}) => {
  return (
    <Form
      layout='vertical'
      initialValues={{
        abstract: '',
        title: ''
      }}
      form={form}
      onFinish={onSubmit}
    >
      <InputFormField
        label='Title'
        name='title'
        tooltip={{ title: 'a short descriptive title for this map context', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Title'
        validation={{
          rules: [{ required: true, message: 'Please input a title for the Map Context!' }],
          hasFeedback: true
        }}
      />
      <InputFormField
        label='Abstract'
        name='abstract'
        tooltip={{ title: 'brief summary of the topic of this map context', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Abstract'
        type='textarea'
        validation={{
          rules: [{ required: true, message: 'Please write an abstract for the Map Context!' }],
          hasFeedback: true
        }}
      />
    </Form>
  );
};