import { SmileOutlined } from '@ant-design/icons';
import { Card, Form, Input, Button, Select, notification } from 'antd';
import { useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { OpenAPIContext } from '../../Hooks/OpenAPIProvider';

const { Option } = Select;

const layout = {
  labelCol: { span: 2 },
  wrapperCol: { span: 8 },
};

const tailLayout = {
  wrapperCol: { offset: 2, span: 8 },
};

export const ServiceEdit = (props: any, context: any) => {

  const navigate = useNavigate();
  const [form] = Form.useForm();
  const { api } = useContext(OpenAPIContext);

  const onFinish = (values: any) => {
    async function postData() {
      console.log(values);
      const client = await api.getClient();
      const res = await client["create/api/v1/registry/ogcservices/"](null, {
        "data": {
          "type": "OgcService",
          "attributes": {
            "get_capabilities_url": values.get_capabilities_url
          },
          "relationships": {
            "owned_by_org": {
              "data": {
                "type": "OgcService",
                "id": values.owned_by_org
              }
            }
          }
        }
      }, { headers: { 'Content-Type': 'application/vnd.api+json' } });

      // const res = await client["List/api/v1/registry/wms/"]({
      //   'page[number]': tableState.page,
      //   'page[size]': tableState.pageSize,
      //   ordering: tableState.ordering,
      //   ...tableState.filters
      // });
      console.log(res);
      if (res.status === 202) {
        notification['info']({
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
    <Card title="Register Service">
      <Form {...layout} form={form} name="control-hooks" onFinish={onFinish}>
        <Form.Item name="get_capabilities_url" label="Capabilities URL" rules={[{ required: true, message: 'Required: Capabilities URL' }]}>
          <Input />
        </Form.Item>
        <Form.Item name="owned_by_org" label="Owner organization" rules={[{ required: true, message: 'Required: Owner organization' }]}>
          <Input />
        </Form.Item>
        <Form.Item {...tailLayout}>
          <Button type="primary" htmlType="submit">
            Submit
          </Button>
          <Button htmlType="button" onClick={onReset}>
            Reset
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
