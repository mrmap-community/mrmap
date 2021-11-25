import './MapContextForm.css';

import { EditFilled, InfoCircleOutlined, MinusCircleFilled, PlusCircleFilled } from '@ant-design/icons';
import { Button, Divider, Form, Modal, notification, Tooltip, Tree } from 'antd';
import { DataNode } from 'antd/lib/tree';
import React, { FC, useEffect, useState } from 'react';

import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import FeatureTypeRepo from '../../Repos/FeatureTypeRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import { InputFormField } from '../Shared/FormFields/InputFormField/InputFormField';
import { SelectAutocompleteFormField } from '../Shared/FormFields/SearchAutocompleteFormField/SearchAutocompleteFormField';
import { SubmitFormButton } from '../Shared/FormFields/SubmitFormButton/SubmitFormButton';

const MAP_CONTEXT_FORM = 'mapContextForm';
const MAP_CONTEXT_LAYER_FORM = 'mapContextLayerForm';

export interface TreeNodeType extends DataNode {
  parent?: string | number;
  children: TreeNodeType[];
  properties?: any;
}
interface MapContextFormProps {
  initTreeData?: TreeNodeType[];
}
interface MapContextLayerFormProps {
  visible: boolean;
  onCancel: () => void;
  isEditing: boolean;
  node: TreeNodeType | undefined;
}

const fetchData = async (
  fetcher: () => void,
  setValues: (values: any) => void,
  setLoading: (bool: boolean) => void
) => {
  setLoading(true);
  try {
    const response:any = await fetcher();
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
const mapContextRepo = new MapContextLayerRepo();

const MapContextLayerForm: FC<MapContextLayerFormProps> = ({ visible, onCancel, isEditing, node }) => {
  const [form] = Form.useForm();

  const [isDatasetMetadataOptionsLoading, setIsDatasetMetadataOptionsLoading] = useState<boolean>(false);
  const [isRenderingLayerOptionsLoading, setIsRenderingLayerOptionsLoading] = useState<boolean>(false);
  const [isFeatureSelectionLayerOptionsLoading, setIsFeatureSelectionLayerOptionsLoading] = useState<boolean>(false);

  const [datasetMetadataOptions, setDatasetMetadataOptions] = useState<any[]>([]);
  const [renderingLayerOptions, setRenderingLayerOptions] = useState<any[]>([]);
  const [featureSelectionLayerOptions, setFeatureSelectionLayerOptions] = useState<any[]>([]);

  const [isShowingRenderingData, setIsShowingRenderingData] = useState<boolean>(false);
  const [isShowingRenderingLayerAttributes, setIsShowingRenderingLayerAttributes] = useState<boolean>(false);
  /**
   * @description: Hook to run on component mount. Fetches initial results for daataset metadata autocomplete
   */
  // useEffect(() => {
  //   fetchData(
  //     () => datasetMetadataRepo.autocomplete(''),
  //     (values) => setDatasetMetadataOptions(values),
  //     (boolean) => setIsDatasetMetadataOptionsLoading(boolean)
  //   );
  // }, []);

  /**
   * @description: Hook to run on component mount. Fetches initial results for rendering layer autocomplete
   */
  useEffect(() => {
    fetchData(
      () => layerRepo.autocomplete(''),
      (values) => setRenderingLayerOptions(values),
      (boolean) => setIsRenderingLayerOptionsLoading(boolean)
    );
  }, []);

  /**
   * @description: Hook to run on component mount. Fetches initial results for rendering feature type selection
   * layers autocomplete
   */
  useEffect(() => {
    fetchData(
      () => featureTypesRepo.autocomplete(''),
      (values) => setFeatureSelectionLayerOptions(values),
      (boolean) => setIsFeatureSelectionLayerOptionsLoading(boolean)
    );
  }, []);

  useEffect(() => {
    if (!isShowingRenderingData) {
      form.resetFields(['renderingLayer']);
    }
  }, [isShowingRenderingData]);

  useEffect(() => {
    if (!isShowingRenderingLayerAttributes) {
      form.resetFields(['scaleMin', 'scaleMax', 'style']);
    }
  }, [isShowingRenderingLayerAttributes]);

  useEffect(() => {
    // since the modal is not being destroyed on close,
    // this is a backup solution. Reseting or setting the values when the modal becomes visible
    if (visible) {
      form.resetFields();
      setIsShowingRenderingData(false);
      setIsShowingRenderingLayerAttributes(false);
      setRenderingLayerOptions([]);
      if (isEditing && node) {
        form.setFieldsValue({
          name: node.properties.name,
          title: node.title
        });
      }
    }
  }, [visible]);

  return (
    <Modal
      title={isEditing ? 'Edit Node' : 'Add Node'}
      visible={visible}
      onOk={() => {
        form.submit();
      }}
      onCancel={onCancel}
      destroyOnClose={true} // not working for some unknown reason
    >
      <Form
        form={form}
        layout='vertical'
        name={MAP_CONTEXT_LAYER_FORM}
        initialValues={{
          name: '',
          title: ''
        }}
      >
      <Divider
        plain
        orientation='left'
      >
        <h3> Metainformation of MapContextLayer </h3>
      </Divider>
        <InputFormField
          label='Name'
          name='name'
          tooltip={{ title: 'an identifying name for this map context layer', icon: <InfoCircleOutlined /> }}
          placeholder='Map Context Layer Name'
          validation={{
            rules: [{ required: true, message: 'Please input a name!' }],
            hasFeedback: true
          }}
        />
        <InputFormField
          label='Title'
          name='title'
          tooltip={{ title: 'a short descriptive title for this map context layer', icon: <InfoCircleOutlined /> }}
          placeholder='Map Context Layer Title'
          validation={{
            rules: [{ required: true, message: 'Please input a title!' }],
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
          searchData={renderingLayerOptions}
          tooltip={{
            title: 'You can use this field to pre filter possible Layer selection.',
            icon: <InfoCircleOutlined />
          }}
          // validation={{
          //   rules: [{ required: true, message: 'Please select metadata!' }],
          //   hasFeedback: true
          // }}
          onSelect={(value, option) => {
            setIsShowingRenderingData(true);
            // TODO set rendering layer list
            // TODO reset dependents
          }}
          onClear={() => {
            setIsShowingRenderingData(false);
            // TODO clear rendering layer list
            // TODO reset dependents
          }}
          onSearch={(value: string) => {
            fetchData(
              () => layerRepo.autocomplete(value),
              (values) => setDatasetMetadataOptions(values),
              (boolean) => setIsDatasetMetadataOptionsLoading(boolean)
            );
          }}
        />

        {isShowingRenderingData && (
          <>
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
              validation={{
                rules: [{ required: true, message: 'Please input a rendering layer!' }],
                hasFeedback: true
              }}
              onSelect={(value, option) => {
                setIsShowingRenderingLayerAttributes(true);
                // fill attribute fields with current layer attributes
                form.setFieldsValue({
                  scaleMin: option.attributes.scaleMin,
                  scaleMax: option.attributes.scaleMax,
                  style: option.attributes.style
                });
              }}
              onSearch={(value: string) => {
                fetchData(
                  () => layerRepo.autocomplete(value),
                  (values) => setRenderingLayerOptions(values),
                  (boolean) => setIsRenderingLayerOptionsLoading(boolean)
                );
              }}
              onClear={() => {
                setIsShowingRenderingLayerAttributes(false);
              }}
            />
            {isShowingRenderingLayerAttributes && (
              <>
                <InputFormField
                  disabled={!form.getFieldValue('scaleMin')}
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
                  disabled={!form.getFieldValue('scaleMax')}
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
                  disabled={!form.getFieldValue('style')}
                  label='Style'
                  name='style'
                  tooltip={{ title: 'Select a style for rendering.', icon: <InfoCircleOutlined /> }}
                  placeholder='Style'
                />
            </>
            )}
          </>
        )}
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
          onSearch={(value: string) => {
            fetchData(
              () => layerRepo.autocomplete(value),
              (values) => setFeatureSelectionLayerOptions(values),
              (boolean) => setIsFeatureSelectionLayerOptionsLoading(boolean)
            );
          }}
        />
      </Form>
    </Modal>
  );
};

export const MapContextForm: FC<MapContextFormProps> = ({
  initTreeData = [
    {
      title: '/',
      key: '0',
      children: [],
      properties: null
    }
  ]
}) => {
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeNodeType[]>(initTreeData);
  const [selectedNode, setSelectedNode] = useState<TreeNodeType>();
  const [isEditing, setIsEditing] = useState<boolean>(false);

  const toggleModal = () => {
    setIsModalVisible(!isModalVisible);
  };

  const updateTreeData = (list: TreeNodeType[], key: React.Key, children: TreeNodeType[]): TreeNodeType[] => {
    return list.map(node => {
      if (node.key === key) {
        return {
          ...node,
          children
        };
      }
      if (node.children) {
        return {
          ...node,
          children: updateTreeData(node.children, key, children)
        };
      }

      return node;
    });
  };

  const getNodeParent = (list: TreeNodeType[], node: TreeNodeType): TreeNodeType[] => {
    return list.reduce((acc: (TreeNodeType[]), value: TreeNodeType) => {
      if (value.key === node.parent) {
        acc.push(value);
        return acc;
      }
      if (value.children) {
        return getNodeParent(value.children, node);
      }
      return acc;
    }, []);
  };

  /**
   * @description: Method to define the action to happen when the user wants to add a new node
   * @param node
   */
  const onAddNode = (node: TreeNodeType | undefined, values: any) => {
    if (node) {
      // mapContextRepo.create(node.key)
      const newNode: TreeNodeType = {
        title: values.title || `${node.key}-${node.children.length}`,
        key: `${node.key}-${node.children.length}`, // this must be  the id of the created node
        children: [],
        parent: node.key,
        properties: values
      };
      //  add here to DB
      // mapContextRepo.create(values)
      setTreeData(updateTreeData(treeData, node.key, [...node.children, newNode]));
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to remove an existing node
   * @param node
   */
  const onRemoveNode = (node: TreeNodeType | undefined) => {
    if (node) {
      const parentNode = getNodeParent(treeData, node);
      if (parentNode.length > 0) {
        const indexToRemove = parentNode[0].children.indexOf(node);
        parentNode[0].children.splice(indexToRemove, 1);
        setTreeData(updateTreeData(treeData, parentNode[0].key, parentNode[0].children));
        // remove here  from db
        // mapContextRepo.delete(node.key)
      }
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to edit an existing node
   * @param node
   */
  const onEditNode = (node: TreeNodeType | undefined, values: any) => {
    if (values && node) {
      node.title = values.title;
      node.properties = values;
    }
  };

  return (
    <Form.Provider
      onFormFinish={(formName, { values, forms }) => {
        const {
          // mapContextForm,
          mapContextLayerForm
        } = forms;
        if (formName === MAP_CONTEXT_LAYER_FORM) {
          if (!isEditing) {
            onAddNode(selectedNode, values);
            // new MapContextLayerRepo().create(values);
            mapContextLayerForm.resetFields();
          } else {
            onEditNode(selectedNode, values);
          }
          // setLayersForSubmission({ mapContextLayers: treeData });
          toggleModal();
        }
        /* eslint-disable-next-line */
        console.log(formName, { ...values, mapContextLayers: treeData });
      }}
    >
      <Form
        name={MAP_CONTEXT_FORM}
        layout='vertical'
        initialValues={{
          abstract: '',
          title: '',
          test: ''
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
        />
        <>
          <h1>Ebenen und Datenangebote</h1>
          <Tree
            className='tree-form-field'
            // draggable={draggable}
            // blockNode
            showIcon
            defaultExpandAll
            // onDragEnter={this.onDragEnter}
            // onDrop={this.onDrop}
            treeData={treeData}
            showLine
            multiple={false}
            // @ts-ignore
            titleRender={
              (nodeData: TreeNodeType):JSX.Element => (
                <div className='tree-form-field-node'>
                  <div className='tree-form-field-node-title'>
                    <h3> {nodeData.title}</h3>
                  </div>
                  <div className='tree-form-field-node-actions'>
                    <Tooltip title='Create Node'>
                      <Button
                        onClick={() => {
                          toggleModal();
                          setSelectedNode(nodeData);
                        }}
                        type='text'
                        icon={<PlusCircleFilled />}
                      />
                    </Tooltip>
                    {nodeData.parent && (
                      <Tooltip title='Remove Node'>
                        <Button
                          onClick={() => {
                            Modal.warning({
                              title: 'Remove Node',
                              content: 'The selectd node will be removed, Are you sure?',
                              onOk: () => { onRemoveNode(nodeData); }
                            });
                          }}
                          type='text'
                          icon={<MinusCircleFilled />}
                        />
                      </Tooltip>
                    )}
                    <Tooltip title='Edit Node'>
                      <Button
                        onClick={() => {
                          toggleModal();
                          setIsEditing(true);
                          setSelectedNode(nodeData);
                        }}
                        type='text'
                        icon={<EditFilled />}
                      />
                    </Tooltip>
                  </div>
                </div>
              )}
            />
        </>
        <SubmitFormButton
          buttonText='Submit'
        />
      </Form>
      <MapContextLayerForm
        visible={isModalVisible}
        onCancel={() => { toggleModal(); setIsEditing(false); }}
        isEditing={isEditing}
        node={selectedNode}
      />
    </Form.Provider>
  );
};
