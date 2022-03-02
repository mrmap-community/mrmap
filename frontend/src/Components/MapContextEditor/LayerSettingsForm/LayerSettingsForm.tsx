import { Form, Input } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import BaseLayer from 'ol/layer/Base';
import { default as React, ReactElement, RefObject, useEffect } from 'react';

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
        title: mapContextLayer.attributes.title
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
    </Form>
  );
};
