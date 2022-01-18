import { InfoCircleOutlined } from '@ant-design/icons';
import { Divider, Form, FormInstance, notification } from 'antd';
import React, { FC, useEffect, useState } from 'react';
import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import FeatureTypeRepo from '../../Repos/FeatureTypeRepo';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';
import { SelectAutocompleteFormField } from '../Shared/FormFields/SelectAutocompleteFormField/SelectAutocompleteFormField';


interface MapContextLayerFormProps {
  form?: FormInstance<any>;
  onSubmit?: (values?:any) => void;
}

const fetchData = async (
  fetcher: () => Promise<JsonApiResponse> | Promise<JsonApiResponse[]>,
  setValues: (values: any) => void,
  setLoading: (bool: boolean) => void
) => {
  setLoading(true);
  try {
    const response = await fetcher();
    setValues(response);
  } catch (error: any) {
    notification.error({
      message: 'Search  failed',
      description: error,
      duration: null
    });
    throw new Error(error);
  } finally {
    setLoading(false);
  }
};

const layerRepo = new LayerRepo();
const datasetMetadataRepo = new DatasetMetadataRepo();
const featureTypesRepo = new FeatureTypeRepo();

export const MapContextLayerForm: FC<MapContextLayerFormProps> = ({
  form = undefined,
  onSubmit = () => undefined,

}) => {
  const [isDatasetMetadataOptionsLoading, setIsDatasetMetadataOptionsLoading] = useState<boolean>(false);
  const [isRenderingLayerOptionsLoading, setIsRenderingLayerOptionsLoading] = useState<boolean>(false);
  const [isFeatureSelectionLayerOptionsLoading, setIsFeatureSelectionLayerOptionsLoading] = useState<boolean>(false);

  const [datasetMetadataOptions, setDatasetMetadataOptions] = useState<any[]>([]);
  const [renderingLayerOptions, setRenderingLayerOptions] = useState<any[]>([]);
  const [featureSelectionLayerOptions, setFeatureSelectionLayerOptions] = useState<any[]>([]);

  const [selectedDatasetMetadata, setSelectedDatasetMetadata] = useState<any>();
  const [selectedRenderingLayer, setSelectedRenderingLayer] = useState<any>();
  const [selectedFeatureSelectionLayer, setSelectedFeatureSelectionLayer] = useState<any>();

  /**
   * @description: Hook to run on component mount. Fetches initial results for daataset metadata autocomplete
   */
  useEffect(() => {
    if (!selectedDatasetMetadata) {
      fetchData(
        () => datasetMetadataRepo.autocomplete(''),
        (values) => setDatasetMetadataOptions(values),
        (boolean) => setIsDatasetMetadataOptionsLoading(boolean)
      );
    }
  }, [selectedDatasetMetadata]);

  // /**
  //  * @description: Hook to run on when value of dataset metadata changes
  //  */
  // useEffect(() => {
  //   if (selectedDatasetMetadata) {
  //     fetchData(
  //       () => layerRepo.getFromIdArray(selectedDatasetMetadata.attributes.associatedLayers),
  //       (values) => setRenderingLayerOptions(values),
  //       (boolean) => setIsRenderingLayerOptionsLoading(boolean)
  //     );
  //   }
  // }, [selectedDatasetMetadata]);

  /**
   * @description: Hook  to run on component mount, if dataset metadata already has a value (on edit form)
   */
  useEffect(() => {
    if (form?.getFieldValue('datasetMetadata')) {
      fetchData(
        () => datasetMetadataRepo.autocompleteInitialValue(form?.getFieldValue('datasetMetadata')),
        (values) => {
          setRenderingLayerOptions([values]);
          setSelectedRenderingLayer(values);
        },
        (boolean) => setIsRenderingLayerOptionsLoading(boolean)
      );
    }
  }, [form]);

  /**
   * @description: Hook to run on component mount. Fetches initial results for rendering layer autocomplete
   */
  useEffect(() => {
    if (!selectedRenderingLayer) {
      fetchData(
        () => layerRepo.autocomplete(''),
        (values) => setRenderingLayerOptions(values),
        (boolean) => setIsRenderingLayerOptionsLoading(boolean)
      );
    }
  }, [selectedRenderingLayer]);

  /**
   * @description: Hook  to run on component mount, if rendering layer already has a value (on edit form)
   */
  useEffect(() => {
    if (form?.getFieldValue('renderingLayer')) {
      fetchData(
        () => layerRepo.autocompleteInitialValue(form?.getFieldValue('renderingLayer')),
        (values) => {
          setRenderingLayerOptions([values]);
          setSelectedRenderingLayer(values);
        },
        (boolean) => setIsRenderingLayerOptionsLoading(boolean)
      );
    }
  }, [form]);

  /**
   * @description: Hook to run on component mount. Fetches initial results for rendering feature type selection
   * layers autocomplete
   */
  useEffect(() => {
    if (!selectedFeatureSelectionLayer) {
      fetchData(
        () => featureTypesRepo.autocomplete(''),
        (values) => setFeatureSelectionLayerOptions(values),
        (boolean) => setIsFeatureSelectionLayerOptionsLoading(boolean)
      );
    }
  }, [selectedFeatureSelectionLayer]);

  /**
   * @description: Hook  to run on component mount, if feature selection layer already has a value (on edit form)
   */
  useEffect(() => {
    if (form?.getFieldValue('featureSelectionLayer')) {
      fetchData(
        () => featureTypesRepo.autocompleteInitialValue(form?.getFieldValue('featureSelectionLayer')),
        (values) => {
          setRenderingLayerOptions([values]);
          setSelectedRenderingLayer(values);
        },
        (boolean) => setIsRenderingLayerOptionsLoading(boolean)
      );
    }
  }, [form]);

  return (
      <Form
        form={form}
        layout='vertical'
        initialValues={{
          title: '',
          description: ''
        }}
        onFinish={(values) => onSubmit(values)}
      >
      <Divider
        plain
        orientation='left'
      >
        <h3> Metainformation of MapContextLayer </h3>
      </Divider>
        <InputFormField
          label='Title'
          name='title'
          tooltip={{ title: 'an identifying name for this map context layer', icon: <InfoCircleOutlined /> }}
          placeholder='Map Context Layer Title'
          validation={{
            rules: [{ required: true, message: 'Please input a title!' }],
            hasFeedback: true
          }}
        />
        <InputFormField
          label='Description'
          name='description'
          tooltip={{ title: 'a short description for this map context layer', icon: <InfoCircleOutlined /> }}
          placeholder='Map Context Layer Description'
          validation={{
            rules: [{ required: true, message: 'Please input a description!' }],
            hasFeedback: true
          }}
        />
        
            <Divider
              plain
              orientation='left'
            >
              <h3> Associated metadata record </h3>
            </Divider>

            <SelectAutocompleteFormField
              loading={isDatasetMetadataOptionsLoading}
              label='Dataset Metadata'
              name='datasetMetadata'
              placeholder='Select Metadata'
              searchData={datasetMetadataOptions}
              tooltip={{
                title: 'You can use this field to pre filter possible Layer selection.',
                icon: <InfoCircleOutlined />
              }}
              // validation={{
              //   rules: [{ required: true, message: 'Please select metadata!' }],
              //   hasFeedback: true
              // }}
              onSelect={(value, option) => {
                setSelectedDatasetMetadata(option);
              }}
              onClear={() => {
                setSelectedDatasetMetadata(undefined);
              }}
              onSearch={(value: string) => {
                fetchData(
                  () => datasetMetadataRepo.autocomplete(value),
                  (values) => setDatasetMetadataOptions(values),
                  (boolean) => setIsDatasetMetadataOptionsLoading(boolean)
                );
              }}
              pagination
            />
            <Divider
              plain
              orientation='left'
            >
              <h3> Rendering options </h3>
            </Divider>

            <SelectAutocompleteFormField
              loading={isRenderingLayerOptionsLoading}
              label='Rendering Layer'
              name='renderingLayer'
              placeholder='Select a rendering layer'
              searchData={renderingLayerOptions}
              tooltip={{ title: 'Select a layer for rendering.', icon: <InfoCircleOutlined /> }}
              // validation={{
              //   rules: [{ required: true, message: 'Please input a rendering layer!' }],
              //   hasFeedback: true
              // }}
              onSelect={(value, option) => {
                setSelectedRenderingLayer(option);
              }}
              onClear={() => {
                setSelectedRenderingLayer(undefined);
              }}
              onSearch={(value: string) => {
                fetchData(
                  () => layerRepo.autocomplete(value),
                  (values) => setRenderingLayerOptions(values),
                  (boolean) => setIsRenderingLayerOptionsLoading(boolean)
                );
              }}
              pagination
            />

            <InputFormField
              disabled={!form?.getFieldValue('scaleMin')}
              label='Scale minimum value'
              name='scaleMin'
              tooltip={{
                title: 'minimum scale for a possible request to this layer. If the request is out of the given' +
                'scope, the service will response with empty transparentimages. None value means no restriction.',
                icon: <InfoCircleOutlined />
              }}
              placeholder='Scale minimum value'
              type='number'
            />

            <InputFormField
              disabled={!form?.getFieldValue('scaleMax')}
              label='Scale maximum value'
              name='scaleMax'
              tooltip={{
                title: 'maximum scale for a possible request to this layer. If the request is out of the given' +
                'scope, the service will response with empty transparentimages. None value means no restriction.',
                icon: <InfoCircleOutlined />
              }}
              placeholder='Scale maximum value'
              type='number'
            />

            <InputFormField
              disabled={!form?.getFieldValue('style')}
              label='Style'
              name='style'
              tooltip={{ title: 'Select a style for rendering.', icon: <InfoCircleOutlined /> }}
              placeholder='Style'
            />
            <Divider
              plain
              orientation='left'
            >
              <h3> Feature selection options </h3>
            </Divider>

            <SelectAutocompleteFormField
              loading={isFeatureSelectionLayerOptionsLoading}
              label='Selection Layer'
              name='featureSelectionLayer'
              placeholder='Select a feature type'
              searchData={featureSelectionLayerOptions}
              tooltip={{ title: ' Select a layer for feature selection.', icon: <InfoCircleOutlined /> }}
              onSelect={(value, option) => {
                setSelectedFeatureSelectionLayer(option);
              }}
              onClear={() => {
                setSelectedFeatureSelectionLayer(undefined);
              }}
              onSearch={(value: string) => {
                fetchData(
                  () => featureTypesRepo.autocomplete(value),
                  (values) => setFeatureSelectionLayerOptions(values),
                  (boolean) => setIsFeatureSelectionLayerOptionsLoading(boolean)
                );
              }}
              pagination
            />
          
      </Form>
  );
};
