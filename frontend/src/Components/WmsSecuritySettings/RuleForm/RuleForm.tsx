import { Button, Form, Input } from 'antd';
import { default as React, ReactElement } from 'react';
import { useNavigate } from 'react-router';

interface RuleFormProps {
    wmsId: string
}

export const RuleForm = ({
  wmsId
}: RuleFormProps): ReactElement => {

  const navigate = useNavigate();
  //   const [groups, setGroups] = useState([]);

  return (
    <>
      <Form         
        layout='vertical'
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

