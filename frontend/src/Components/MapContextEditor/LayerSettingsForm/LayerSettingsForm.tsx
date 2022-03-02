import { LinkOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { Button, Col, Divider, Form, Input, InputNumber, Row, Slider, Space, Switch } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import BaseLayer from 'ol/layer/Base';
import { default as React, ReactElement, RefObject, useEffect } from 'react';
import { InputField } from '../../Shared/FormFields/InputField/InputField';

interface LayerSettingsFormProps {
    selectedLayer?: BaseLayer;
    titleInputRef: RefObject<any>;
}

export const LayerSettingsForm = ({
  selectedLayer,
  titleInputRef
}: LayerSettingsFormProps
): ReactElement => {

  const [form] = useForm();
  const innerTitleInputRef = titleInputRef;

  useEffect( () => {
    if (selectedLayer) {
      const mapContextLayer = selectedLayer.get('mapContextLayer');
      form.setFieldsValue({
        title: mapContextLayer.attributes.title,
        description: mapContextLayer.attributes.description
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
    <Form
      form={form}
      layout='vertical'
    >
      <Divider>Beschreibende Informationen</Divider>
      <Row>
        <Col span={11}>
          <Form.Item
            label='Titel'
            name='title'
          >
            <Input
              placeholder='Ein identifizierender Name für diese MapContext Ebene'
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <InputField
            label='Beschreibung'
            name='description'
            placeholder='Eine Kurzbeschreibung für diese MapContext Ebene'
          />
        </Col>
      </Row>
      <Divider>Maßstabsbereich</Divider>
      <Row>
        <Col span={23}><Slider range defaultValue={[20, 50]} /></Col>
      </Row>
      <Row>
        <Col span={11}>
          <Form.Item
            label='Minimaler Maßstabswert'
            name='minResolution'
          >
            <Space>
              <Switch />
              <InputNumber min={0} max={1000000} defaultValue={0} />
              <Button>Aus Karte</Button>
            </Space>
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            label='Maximaler Maßstabswert'
            name='maxResolution'
          >
            <Space>
              <Switch />
              <InputNumber min={0} max={1000000} defaultValue={0} />
              <Button>Aus Karte</Button>
            </Space>
          </Form.Item>
        </Col>
      </Row>

      <Divider><LinkOutlined/>&nbsp;&nbsp;Verknüpfte Ressourcen</Divider>
      <Row>
        <Col span={11}>
          <Form.Item
            label={<><FontAwesomeIcon icon='file'/>&nbsp;&nbsp;&nbsp;Metadatensatz</>}
          >
            <Input
              placeholder='Der mit dieser Ebene verknüpfte Metadatensatz'
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            label={
              <><FontAwesomeIcon icon='crosshairs' />&nbsp;&nbsp;&nbsp;Selektionsebene (WMS-Layer / WFS-FeatureType)</>
            }
          >
            <Input
              placeholder='Der mit dieser Ebene verknüpfte Metadatensatz'
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row>
        <Col span={11}>
          <Form.Item
            label={<><FontAwesomeIcon icon='eye'/>&nbsp;&nbsp;&nbsp;Darstellungsebene (WMS-Layer)</>}
          >
            <Input
              placeholder='Der mit dieser Ebene verknüpfte Metadatensatz'
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
        <Col span={1} />
        <Col span={11}>
          <Form.Item
            label={<><FontAwesomeIcon icon='eye'/>&nbsp;&nbsp;&nbsp;Darstellungsstil</>}
          >
            <Input
              placeholder='Der mit dieser Ebene verknüpfte Metadatensatz'
              onPressEnter={onTitleEntered}
              ref={innerTitleInputRef}
            />
          </Form.Item>
        </Col>
      </Row>
    </Form>
  );
};
