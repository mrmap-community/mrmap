import { Button, Form, Input, notification } from 'antd';
import { default as React, ReactElement } from 'react';
import { useNavigate } from 'react-router';
import WmsAllowedOperationRepo, { WmsAllowedOperationCreate } from '../../../Repos/WmsAllowedOperationRepo';

interface RuleFormProps {
    wmsId: string
}

export const RuleForm = ({
  wmsId
}: RuleFormProps): ReactElement => {

  const navigate = useNavigate();
  //   const [groups, setGroups] = useState([]);

  const ruleRepo = new WmsAllowedOperationRepo(wmsId);

  const onFinish = (values: any) => {

    const create: WmsAllowedOperationCreate = {
      title: values.title,
      securedLayerIds: ['2da5a138-7c80-4841-8e80-a4462685e3e1'],
      allowedOperationIds: ['GetMap', 'GetFeatureInfo'],
      allowedGroupIds: ['1']
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
        <Form.Item
          name='title'
          label='Titel'
          required={true}
        >
          <Input />
        </Form.Item>
        <Form.Item>
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
        </Form.Item>                
      </Form>
    </>
  );
};

