import { InfoCircleOutlined } from '@ant-design/icons';
import { Button, Card, Checkbox, Form, Input, notification } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { OgcServiceRepo } from '../../Repos/OgcServiceRepo';
import OrganizationRepo from '../../Repos/OrganizationRepo';
import { SearchFieldData, SelectAutocompleteFormField } from '../Shared/FormFields/SelectAutocompleteFormField/SelectAutocompleteFormField';

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

  const [options, setOptions] = useState<SearchFieldData[]>([]);
  const [isLoading, setLoading] = useState(false);

  const navigate = useNavigate();

  const onFinish = (values: any) => {
    async function postData () {
      const res = await repo.create(values);
      if (res.status === 202) {
        notification.info({
          message: 'Service registration job started',
          description: 'Your service registration job has been accepted and is being processed'
        });
        navigate(-1);
      }
    }
    postData();
  };

  async function fetchOrgOptions (orgName: string) {
    setLoading(true);
    setOptions(await organizationRepo.autocomplete(orgName));
    setLoading(false);
  }

  useEffect(() => {
    fetchOrgOptions('');
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
          collect_metadata_records: false // eslint-disable-line
        }}
      >
        <Form.Item
          name='get_capabilities_url'
          label='Capabilities URL'
          rules={[{ required: true, message: 'Required: Capabilities URL' }]}
        >
          <Input />
        </Form.Item>

        <SelectAutocompleteFormField
          loading={isLoading}
          label='Owner organization'
          name='owner'
          placeholder='Select Organization'
          searchData={options}
          tooltip={{
            title: 'You can use this field to pre filter possible organization selection.',
            icon: <InfoCircleOutlined />
          }}
          validation={{
            rules: [{ required: true, message: 'Required: Owner organization' }],
            hasFeedback: false
          }}
          onSearch={(value: string) => {
            fetchOrgOptions(value);
          }}
        />

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
