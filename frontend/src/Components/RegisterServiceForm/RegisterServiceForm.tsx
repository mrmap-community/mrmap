import { InfoCircleOutlined } from '@ant-design/icons';
import { Button, Card, Checkbox, Form, Input, notification } from 'antd';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import JsonApiRepo from '../../Repos/JsonApiRepo';
import OrganizationRepo from '../../Repos/OrganizationRepo';
import { SearchFieldData, SelectAutocompleteField } from '../Shared/FormFields/SelectAutocompleteField/SelectAutocompleteField';

interface RegisterServiceFormProps {
  repo: JsonApiRepo;
}
const layout = {
  labelCol: { span: 3 },
  wrapperCol: { span: 8 }
};

const tailLayout = {
  wrapperCol: { offset: 3, span: 8 }
};

const organizationRepo = new OrganizationRepo();

const RegisterServiceForm = ({
  repo
}: RegisterServiceFormProps): ReactElement => {

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
          collectMetadataRecords: false
        }}
      >
        <Form.Item
          name='getCapabilitiesUrl'
          label='Capabilities URL'
          rules={[{ required: true, message: 'Required: Capabilities URL' }]}
        >
          <Input />
        </Form.Item>

        <SelectAutocompleteField
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
          name='collectMetadataRecords'
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

export default RegisterServiceForm;
