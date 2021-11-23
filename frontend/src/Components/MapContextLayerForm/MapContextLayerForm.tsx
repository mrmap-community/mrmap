import { InfoCircleOutlined } from '@ant-design/icons';
import { Divider, Form } from 'antd';
import React, { FC } from 'react';

import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';
import { SearchAutocompleteFormField } from '../Shared/FormFields/SearchAutocompleteFormField/SearchAutocompleteFormField';

const datasetMetadataData = [
  {
    value: '1',
    text: 'Dataset 1'
  },
  {
    value: '2',
    text: 'Dataset 2'
  },
  {
    value: '3',
    text: 'Dataset 3'
  }
];

const layerData = [
  {
    value: '1',
    text: 'Layer 1'
  },
  {
    value: '2',
    text: 'Layer 2'
  },
  {
    value: '3',
    text: 'Layer 3'
  }
];

interface MapContextLayerFormProps {}

export const MapContextLayerForm: FC<MapContextLayerFormProps> = () => {
  return (
    <>
      <Divider plain orientation="left">
        <h3> Metainformation of MapContextLayer </h3>
      </Divider>

      <InputFormField
        label="Name"
        name='name'
        tooltip={{ title: 'an identifying name for this map context layer', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Layer Name'
      />

      <InputFormField
        label="Title"
        name='title'
        tooltip={{ title: 'a short descriptive title for this map context layer', icon: <InfoCircleOutlined /> }}
        placeholder='Map Context Layer Title'
        validation={{
          rules: [{ required: true, message: 'Please input a title!' }],
          errorHelp: '',
          hasFeedback: true,
          feedbackStatus: 'success'
        }}
      />

      {/* <Divider plain orientation="left">
        <h3> Associated metadata record </h3>
      </Divider>

      <SearchAutocompleteFormField
        showSearch
        label="Dataset Metadata"
        name={`${name}.datasetMetadata`}
        placeholder='Select Metadata'
        searchData={datasetMetadataData}
        tooltip={{
          title: 'You can use this field to pre filter possible Layer selection.',
          icon: <InfoCircleOutlined />
        }}
      />

      <Divider plain orientation="left">
        <h3> Rendering options </h3>
      </Divider>

      <SearchAutocompleteFormField
        showSearch
        label="Rendering Layer"
        name={`${name}.renderingLayer`}
        placeholder='Select a rendering layer'
        searchData={layerData}
        tooltip={{ title: 'Select a layer for rendering.', icon: <InfoCircleOutlined /> }}
      />

      <InputFormField
        label="Scale minimum value"
        name={`${name}.scaleMin`}
        tooltip={{
          title: 'minimum scale for a possible request to this layer. If the request is out of the given scope, the service will response with empty transparentimages. None value means no restriction.',
          icon: <InfoCircleOutlined />
        }}
        placeholder='Scale minimum value'
        type='number'
      />

      <InputFormField
        label="Scale maximum value"
        name={`${name}.scaleMax`}
        tooltip={{
          title: 'maximum scale for a possible request to this layer. If the request is out of the given scope, the service will response with empty transparentimages. None value means no restriction.',
          icon: <InfoCircleOutlined />
        }}
        placeholder='Scale maximum value'
        type='number'
      />

      <InputFormField
        label="Style"
        name={`${name}.style`}
        tooltip={{ title: 'Select a style for rendering.', icon: <InfoCircleOutlined /> }}
        placeholder='Style'
      />

      <Divider plain orientation="left">
        <h3> Feature selection options </h3>
      </Divider>

      <SearchAutocompleteFormField
        showSearch
        label="Selection Layer"
        name={`${name}.featureSelectionLayer`}
        placeholder='Select a feature type'
        searchData={layerData}
        tooltip={{ title: ' Select a layer for feature selection.', icon: <InfoCircleOutlined /> }}
      /> */}
    </>
  );
};
