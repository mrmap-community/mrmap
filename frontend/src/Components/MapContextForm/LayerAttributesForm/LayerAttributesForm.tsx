import { InfoCircleOutlined, SyncOutlined } from '@ant-design/icons';
import { Divider, Form, FormInstance, notification } from 'antd';
import React, { FC, useEffect, useState } from 'react';
import DatasetMetadataRepo from '../../../Repos/DatasetMetadataRepo';
import FeatureTypeRepo from '../../../Repos/FeatureTypeRepo';
import { JsonApiResponse } from '../../../Repos/JsonApiRepo';
import LayerRepo from '../../../Repos/LayerRepo';
import { InputField } from '../../Shared/FormFields/InputField/InputField';
import { SelectAutocompleteField } from '../../Shared/FormFields/SelectAutocompleteField/SelectAutocompleteField';
import { TreeNodeType } from '../../Shared/TreeManager/TreeManagerTypes';


interface LayerAttributesFormProps {
  form?: FormInstance<any>;
  onSubmit?: (values?:any) => void;
  nodeInfo?: TreeNodeType | undefined;
  showBasicInfo?: boolean;
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
      message: 'Search failed',
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

export const LayerAttributesForm: FC<LayerAttributesFormProps> = ({
  form = undefined,
  onSubmit = () => undefined,
  nodeInfo = undefined,
  showBasicInfo = false
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

  const datasetMetadataInitValue = form?.getFieldValue('datasetMetadata');
  const renderingLayerValue = form?.getFieldValue('renderingLayer');
  const featureSelectionLayerInitValue = form?.getFieldValue('featureSelectionLayer');

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
    // cleanup on unmount
    return () => {
      setSelectedDatasetMetadata(undefined);
      setDatasetMetadataOptions([]);
      setIsDatasetMetadataOptionsLoading(false);
    };
  }, [selectedDatasetMetadata]);

  /**
   * @description: Hook  to run on component mount, if dataset metadata already has a value (on edit form)
   */
  useEffect(() => {
    if(form && datasetMetadataInitValue) {
      const currentSelecteDatasetMetadataId = datasetMetadataInitValue;
      if(currentSelecteDatasetMetadataId) {
        fetchData(
          () => datasetMetadataRepo.autocompleteInitialValue(currentSelecteDatasetMetadataId),
          (values) => {
            setDatasetMetadataOptions([values]);
            setSelectedDatasetMetadata(values);
          },
          (boolean) => setIsDatasetMetadataOptionsLoading(boolean)
        );
      }
    }
  }, [form, datasetMetadataInitValue]);

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
    // cleanup on unmount
    return () => {
      setSelectedRenderingLayer(undefined);
      setRenderingLayerOptions([]);
      setIsRenderingLayerOptionsLoading(false);
    };
  }, [selectedRenderingLayer]);

  /**
   * @description: Hook  to run on component mount, if rendering layer already has a value (on edit form)
   */
  useEffect(() => {
    if(form && renderingLayerValue) {
      const currentSelecteRenderingLayerId = renderingLayerValue;
      if(currentSelecteRenderingLayerId) {
        fetchData(
          () => layerRepo.autocompleteInitialValue(currentSelecteRenderingLayerId),
          (values) => {
            setRenderingLayerOptions([values]);
            setSelectedRenderingLayer(values);
          },
          (boolean) => setIsRenderingLayerOptionsLoading(boolean)
        );
      }
    }
  }, [form, renderingLayerValue]);

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
    // cleanup on unmount
    return () => {
      setSelectedFeatureSelectionLayer(undefined);
      setFeatureSelectionLayerOptions([]);
      setIsFeatureSelectionLayerOptionsLoading(false);
    };
  }, [selectedFeatureSelectionLayer]);

  /**
   * @description: Hook  to run on component mount, if feature selection layer already has a value (on edit form)
   */
  useEffect(() => {
    if(form && featureSelectionLayerInitValue) {
      const currentSelecteFeatureSelectionLayerId = featureSelectionLayerInitValue;
      if(currentSelecteFeatureSelectionLayerId) {
        fetchData(
          () => featureTypesRepo.autocompleteInitialValue(currentSelecteFeatureSelectionLayerId),
          (values) => {
            setFeatureSelectionLayerOptions([values]);
            setSelectedFeatureSelectionLayer(values);
          },
          (boolean) => setIsRenderingLayerOptionsLoading(boolean)
        );
      }
    }
  }, [form, featureSelectionLayerInitValue]);

  if(!nodeInfo) {
    return (<SyncOutlined spin />);
  }
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
      {(
        !nodeInfo.isLeaf || (nodeInfo.isLeaf && !nodeInfo.properties.title && !nodeInfo.properties.description)
      ) && (
        <>
          <Divider
            plain
            orientation='left'
          >
            <h3> Metainformation of MapContextLayer </h3>
          </Divider>

          <InputField
            label='Title'
            name='title'
            tooltip={{ title: 'an identifying name for this map context layer', icon: <InfoCircleOutlined /> }}
            placeholder='Map Context Layer Title'
            validation={{
              rules: [{ required: true, message: 'Please input a title!' }],
              hasFeedback: true
            }}
          />

          <InputField
            label='Description'
            name='description'
            tooltip={{ title: 'a short description for this map context layer', icon: <InfoCircleOutlined /> }}
            placeholder='Map Context Layer Description'
            validation={{
              rules: [{ required: true, message: 'Please input a description!' }],
              hasFeedback: true
            }}
          />
        </>
      )}
      
      {(!showBasicInfo || nodeInfo.isLeaf) && (
        <>
          <Divider
            plain
            orientation='left'
          >
            <h3> Associated metadata record </h3>
          </Divider>

          <SelectAutocompleteField
            loading={isDatasetMetadataOptionsLoading}
            label='Dataset Metadata'
            name='datasetMetadata'
            placeholder='Select Metadata'
            searchData={datasetMetadataOptions}
            tooltip={{
              title: 'You can use this field to pre filter possible Layer selection.',
              icon: <InfoCircleOutlined />
            }}
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

          <SelectAutocompleteField
            loading={isRenderingLayerOptionsLoading}
            label='Rendering Layer'
            name='renderingLayer'
            placeholder='Select a rendering layer'
            searchData={renderingLayerOptions}
            tooltip={{ title: 'Select a layer for rendering.', icon: <InfoCircleOutlined /> }}
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

          <InputField
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

          <InputField
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

          <InputField
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

          <SelectAutocompleteField
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
        </>
      )}
    </Form>
  );
};
