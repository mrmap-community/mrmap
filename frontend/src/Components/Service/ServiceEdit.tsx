import { Button, Card, Form, Input, notification } from 'antd';
import React from 'react';

import OgcServices from '../../Services/OgcServices';

const layout = {
  labelCol: { span: 3 },
  wrapperCol: { span: 8 }
};

const tailLayout = {
  wrapperCol: { offset: 3, span: 8 }
};

export const ServiceEdit = (props: any, context: any) => {
  const [form] = Form.useForm();

  const onFinish = (values: any) => {
    async function postData () {
      console.log(values);
      const res = await new OgcServices().create(values);
      console.log(res);
      if (res.status === 202) {
        notification.info({
          message: 'Service registration job started',
          description: 'Your service registration job has been accepted and is being processed'
        });
      }
    }
    postData();
  };

  const onReset = () => {
    form.resetFields();
  };

  return (
    <Card title='Register Service'>
      <Form
        {...layout}
        form={form}
        name='control-hooks'
        onFinish={onFinish}
      >
        <Form.Item
          name='get_capabilities_url'
          label='Capabilities URL'
          rules={[{ required: true, message: 'Required: Capabilities URL' }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name='owned_by_org'
          label='Owner organization'
          rules={[{ required: true, message: 'Required: Owner organization' }]}
        >
          <Input />
        </Form.Item>
        <Form.Item {...tailLayout}>
          <Button
            type='primary'
            htmlType='submit'
          >
            Submit
          </Button>
          <Button
            htmlType='button'
            onClick={onReset}
          >
            Reset
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
