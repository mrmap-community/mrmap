import './MapContextForm.css';

import InfoCircleOutlined from '@ant-design/icons/lib/icons/InfoCircleOutlined';
import { Divider, Form } from 'antd';
import { Content } from 'antd/lib/layout/layout';
import { format } from 'path/posix';
import React, { FC, useState } from 'react';

import { MapContextLayerForm } from '../MapContextLayerForm/MapContextLayerForm';
import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';
import { SearchAutocompleteFormField } from '../Shared/FormFields/SearchAutocompleteFormField/SearchAutocompleteFormField';
import { SubmitFormButton } from '../Shared/FormFields/SubmitFormButton/SubmitFormButton';
import { TreeFormField } from '../Shared/FormFields/TreeFormField/TreeFormField';

interface MapContextFormProps {}

export const MapContextForm: FC<MapContextFormProps> = () => {
  const [mapContextLayers, setMapContextLayers] = useState([]);
  return (
    <Form
      layout="vertical"
      onFinish={(values) => { console.log(values); }}
      onValuesChange={(changedValues, allValues) => { console.log(changedValues, allValues); }}
      initialValues={{
        title: '',
        abstract: '',
        mapContextLayers: []
      }}
    >
      <InputFormField
        label="Title"
        name="title"
        tooltip={{ title: 'a short descriptive title for this map context', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Title'
      />
      <InputFormField
        label="Abstract"
        name="abstract"
        tooltip={{ title: 'brief summary of the topic of this map context', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Abstraact'
        type='textarea'
      />
      <TreeFormField
        name='mapContextLayers'
        title='Ebenen und Datenangebote'
        onTreeChange={(values) => setMapContextLayers(values) }
      />
      <SubmitFormButton
        buttonText='Submit'
      />
    </Form>
  );
};
