import { InfoCircleOutlined } from '@ant-design/icons';
import { Button, Form } from 'antd';
import React, { FC, useState } from 'react';

import MapContextRepo from '../../Repos/MapContextRepo';
import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';
import { TreeNodeType } from './MapContextForm';

interface MapContextFormProps {
  initTreeData?: TreeNodeType[];
  onStepChange?: () => void;
  setCreatedMapContextId?: (id: string) => void;
}

const mapContextRepo = new MapContextRepo();

export const MapContextForm: FC<MapContextFormProps> = ({
  onStepChange = () => undefined,
  setCreatedMapContextId = () => undefined
}) => {
  const [isSubmittingForm, setIsSubmittingForm] = useState<boolean>(false);

  return (
    <Form
      layout='vertical'
      initialValues={{
        abstract: '',
        title: ''
      }}
      onFinish={async (values) => {
        setIsSubmittingForm(true);
        try {
          const response = await mapContextRepo.create(values);
          setCreatedMapContextId(response.data.data.id);
          return response;
        } catch (error) {
          setIsSubmittingForm(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsSubmittingForm(false);
          onStepChange();
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
      <div className='steps-action'>
        <Button
          type='primary'
          htmlType='submit'
          disabled={isSubmittingForm}
          loading={isSubmittingForm}
        >
          Next Step
        </Button>
      </div>
    </Form>
  );
};
