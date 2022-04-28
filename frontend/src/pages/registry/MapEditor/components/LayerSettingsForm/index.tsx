import InputField from '@/components/InputField';
import { LinkOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { Button, Col, Divider, Form, Input, InputNumber, Row, Slider, Space, Switch } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import type BaseLayer from 'ol/layer/Base';
import type { ReactElement, RefObject } from 'react';
import { useEffect } from 'react';
import { FormattedMessage, useIntl } from 'umi';

interface LayerSettingsFormProps {
  selectedLayer?: BaseLayer;
  titleInputRef: RefObject<any>;
}

const LayerSettingsForm = ({
  selectedLayer,
  titleInputRef,
}: LayerSettingsFormProps): ReactElement => {
  const intl = useIntl();
  const [form] = useForm();
  const innerTitleInputRef = titleInputRef;

  useEffect(() => {
    if (selectedLayer) {
      const mapContextLayer = selectedLayer.get('mapContextLayer');
      form.setFieldsValue({
        title: mapContextLayer.attributes.title,
        description: mapContextLayer.attributes.description,
      });
    } else {
      form.resetFields();
    }
  }, [selectedLayer, form]);

  const onTitleEntered = () => {
    if (selectedLayer) {
      const mapContextLayer = selectedLayer.get('mapContextLayer');
      const newTitle = form.getFieldValue('title');
      if (mapContextLayer.attributes.title !== newTitle) {
        mapContextLayer.attributes.title = newTitle;
        selectedLayer.set('mapContextLayer', { ...mapContextLayer });
      }
    }
    innerTitleInputRef.current?.blur();
  };

  return (
    <Form form={form} layout="vertical">
      <Divider>
        <FormattedMessage id="pages.mapEditor.layerSettingsForm.metadata" />
      </Divider>
      <Row>
        <Col span={11}>
          <Form.Item
            name="title"
            label={intl.formatMessage({ id: 'pages.mapEditor.layerSettingsForm.titleLabel' })}
          >
            <Input
              placeholder={intl.formatMessage({
                id: 'pages.mapEditor.layerSettingsForm.titlePlaceholder',
              })}
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <InputField
            name="description"
            label={intl.formatMessage({ id: 'pages.mapEditor.layerSettingsForm.descriptionLabel' })}
            placeholder={intl.formatMessage({
              id: 'pages.mapEditor.layerSettingsForm.descriptionPlaceholder',
            })}
          />
        </Col>
      </Row>
      <Divider>
        <FormattedMessage id="pages.mapEditor.layerSettingsForm.dimensionRange" />
      </Divider>
      <Row>
        <Col span={23}>
          <Slider range defaultValue={[20, 50]} />
        </Col>
      </Row>
      <Row>
        <Col span={11}>
          <Form.Item
            name="minResolution"
            label={intl.formatMessage({
              id: 'pages.mapEditor.layerSettingsForm.minResolutionLabel',
            })}
          >
            <Space>
              <Switch />
              <InputNumber min={0} max={1000000} defaultValue={0} />
              <Button>
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.fromMap" />
              </Button>
            </Space>
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            name="maxResolution"
            label={intl.formatMessage({
              id: 'pages.mapEditor.layerSettingsForm.maxResolutionLabel',
            })}
          >
            <Space>
              <Switch />
              <InputNumber min={0} max={1000000} defaultValue={0} />
              <Button>
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.fromMap" />
              </Button>
            </Space>
          </Form.Item>
        </Col>
      </Row>
      <Divider>
        <LinkOutlined />
        &nbsp;&nbsp;
        <FormattedMessage id="pages.mapEditor.layerSettingsForm.linkedResources" />
      </Divider>
      <Row>
        <Col span={11}>
          <Form.Item
            label={
              <>
                <FontAwesomeIcon icon="file" />
                &nbsp;&nbsp;&nbsp;
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.metadataSetLabel" />
              </>
            }
          >
            <Input
              placeholder={intl.formatMessage({
                id: 'pages.mapEditor.layerSettingsForm.metadataSetPlaceholder',
              })}
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            label={
              <>
                <FontAwesomeIcon icon="crosshairs" />
                &nbsp;&nbsp;&nbsp;
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.selectionLayerLabel" />
              </>
            }
          >
            <Input
              placeholder={intl.formatMessage({
                id: 'pages.mapEditor.layerSettingsForm.metadataSetPlaceholder',
              })}
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row>
        <Col span={11}>
          <Form.Item
            label={
              <>
                <FontAwesomeIcon icon="eye" />
                &nbsp;&nbsp;&nbsp;
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.viewLayerLabel" />
              </>
            }
          >
            <Input
              placeholder={intl.formatMessage({
                id: 'pages.mapEditor.layerSettingsForm.metadataSetPlaceholder',
              })}
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            label={
              <>
                <FontAwesomeIcon icon="eye" />
                &nbsp;&nbsp;&nbsp;
                <FormattedMessage id="pages.mapEditor.layerSettingsForm.viewLayerStyle" />
              </>
            }
          >
            <Input
              placeholder={intl.formatMessage({
                id: 'pages.mapEditor.layerSettingsForm.metadataSetPlaceholder',
              })}
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
      </Row>
    </Form>
  );
};

export default LayerSettingsForm;
