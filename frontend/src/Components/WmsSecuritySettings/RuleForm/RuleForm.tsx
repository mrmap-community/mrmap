import { Button, Form, notification, Space } from 'antd';
import { default as React, ReactElement } from 'react';
import { useNavigate } from 'react-router';
import WmsAllowedOperationRepo, { WmsAllowedOperationCreate } from '../../../Repos/WmsAllowedOperationRepo';
import { InputField } from '../../Shared/FormFields/InputField/InputField';

interface RuleFormProps {
    wmsId: string,
    selectedLayerIds: string[]
}

export const RuleForm = ({
  wmsId,
  selectedLayerIds
}: RuleFormProps): ReactElement => {

  const ruleRepo = new WmsAllowedOperationRepo(wmsId);

  const navigate = useNavigate();

  const onFinish = (values: any) => {
    const create: WmsAllowedOperationCreate = {
      description: values.description,
      securedLayerIds: selectedLayerIds,
      allowedOperationIds: ['GetMap'], // TODO
      allowedGroupIds: [] // TODO
    };

    async function postData () {
      const res = await ruleRepo.create(create);
      if (res.status === 201) {
        notification.info({
          message: 'WMS security rule created',
          description: 'Your WMS security rule has been created'
        });
        navigate(`/registry/services/wms/${wmsId}/security`);
      }
    }
    postData();
  };

  return (
    <>
      <Form         
        layout='vertical'
        onFinish={onFinish}
      >
        <InputField
          label='Description'
          name='description'
          placeholder='Short description of the security rule'
          validation={{
            rules: [{ required: true, message: 'Please input a description!' }],
            hasFeedback: true
          }}          
        />
        <Form.Item>
          <Space>
            <Button
              type='primary'
              htmlType='submit'
            >
              Speichern
            </Button>
            <Button
              htmlType='button'
              onClick={ () => navigate(`/registry/services/wms/${wmsId}/security`)}
            >
              Abbrechen
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </>
  );
};
