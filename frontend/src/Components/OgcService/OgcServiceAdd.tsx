import { Button, Card, Checkbox, Form, Input, notification, Select } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';

import { OgcServiceRepo } from '../../Repos/OgcServiceRepo';
import OrganizationRepo from '../../Repos/OrganizationRepo';

const layout = {
  labelCol: { span: 3 },
  wrapperCol: { span: 8 }
};

const tailLayout = {
  wrapperCol: { offset: 3, span: 8 }
};

const repo = new OgcServiceRepo();
const organizationRepo = new OrganizationRepo();

export const OgcServiceAdd = (): ReactElement => {
  const [form] = Form.useForm();

  const [options, setOptions] = useState<{ label: string, value: string }[]>([]);
  const [isLoading, setLoading] = useState(false);

  const onFinish = (values: any) => {
    async function postData () {
      const res = await repo.create(values);
      if (res.status === 202) {
        notification.info({
          message: 'Service registration job started',
          description: 'Your service registration job has been accepted and is being processed'
        });
      }
    }
    postData();
  };

  useEffect(() => {
    async function fetchOrgOptions () {
      setLoading(true);
      setOptions(await organizationRepo.autocomplete(''));
      setLoading(false);
    }
    fetchOrgOptions();
  }, []);

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
        initialValues={{
          collect_metadata_records: false
        }}
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
          rules={[{ required: true, message: 'Required: Owner organization' }]}>
          <Select
            showSearch
            style={{ width: 200 }}
            placeholder='Select an organization'
            optionFilterProp='label'
            filterOption={true}
            options={options}
            loading={isLoading}
          />
        </Form.Item >
        <Form.Item
          name='collect_metadata_records'
          label='Collect metadata records'
          valuePropName='checked'
        >
          <Checkbox/>
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

export default OgcServiceAdd;
