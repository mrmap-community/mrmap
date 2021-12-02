import { InfoCircleOutlined } from '@ant-design/icons';
import { Form } from 'antd';
import React, { FC } from 'react';

import MapContextRepo from '../../Repos/MapContextRepo';
import { hasOwnProperty } from '../../utils';
import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';

interface MapContextFormProps {
  form?: any;
  setIsSubmittingMapContext?: (bool: boolean) => void;
  setCreatedMapContextId?: (id: string) => void;
  onSubmit?:()=>void;
}

const mapContextRepo = new MapContextRepo();

export const MapContextForm: FC<MapContextFormProps> = ({
  form = undefined,
  setIsSubmittingMapContext = () => undefined,
  setCreatedMapContextId = () => undefined,
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
      onFinish={async (values) => {
        setIsSubmittingMapContext(true);
        try {
          const response = await mapContextRepo.create(values);
          if (response.data?.data &&
            hasOwnProperty(response.data.data, 'id')) {
            setCreatedMapContextId(response.data.data.id);
          }
          return response;
        } catch (error) {
          setIsSubmittingMapContext(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsSubmittingMapContext(false);
          onSubmit();
        }
      }}
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
