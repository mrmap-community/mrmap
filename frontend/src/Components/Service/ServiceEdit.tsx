import { AutoComplete, Button, Card, Form, Input, notification } from 'antd';
import React, { ReactElement, useState } from 'react';

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

export const ServiceEdit = (): ReactElement => {
  const [form] = Form.useForm();

  const [options, setOptions] = useState<{ id: string, value: string }[]>([]);
  const [isLoading, setLoading] = useState(false);

  const onSearch = (searchText: string) => {

    async function autocomplete() {
      setLoading(true);
      try {
        const res: any = await organizationRepo.autocomplete(searchText);
        console.log(res);
        setOptions(res);
      } catch (err) {
        // TODO centralise error notification
        notification['error']({
          message: "Autocompletion failed",
          description: "" + err,
          duration: null
        });
        throw err;
      } finally {
        setLoading(false);
      }
    }

    autocomplete();
  };
  const onSelect = (data: string) => {
    console.log('onSelect', data);
  };

  const onFinish = (values: any) => {
    async function postData() {
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
          rules={[{ required: true, message: 'Required: Owner organization' }]}>
          <AutoComplete
            options={options}
            style={{ width: 200 }}
            onSelect={onSelect}
            onSearch={onSearch}
          >
            <Input.Search placeholder="input here" loading={isLoading} />
          </AutoComplete>
        </Form.Item >

        {/* <SearchAutocompleteFormField name='owned_by_org' label='Owner organization' validation={{
          rules: [{ required: true, message: 'Required: Owner organization' }],
          hasFeedback: false,
        }} placeholder='' searchData={[{
          value: '1',
          text: 'Dataset 1'
        },
        {
          value: '2',
          text: 'Dataset 2'
        },
        {
          value: '3',
          text: 'Dataset 3'
        }]} showSearch/> */}

        {/* <Form.Item
          name='owned_by_org'
          label='Owner organization'
          rules={[{ required: true, message: 'Required: Owner organization' }]}
        >
          <Input />
        </Form.Item> */}
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
