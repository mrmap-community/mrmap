import { Alert, Button, Form, notification, Select, Space } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import TextArea from 'antd/lib/input/TextArea';
import { default as React, ReactElement, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../../Hooks/useAuth';
import { operation } from '../../../Repos/JsonApi';
import WmsAllowedOperationRepo, { WmsAllowedOperationCreate } from '../../../Repos/WmsAllowedOperationRepo';
import WmsOperationRepo from '../../../Repos/WmsOperationRepo';
import { InputField } from '../../Shared/FormFields/InputField/InputField';

const { Option } = Select;

const wmsOpRepo = new WmsOperationRepo();

interface RuleFormProps {
    wmsId: string,
    selectedLayerIds: string[],
    setSelectedLayerIds: (ids: string[]) => void    
}

export const RuleForm = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds
}: RuleFormProps): ReactElement => {

  const ruleRepo = new WmsAllowedOperationRepo(wmsId);

  const navigate = useNavigate();
  const { ruleId } = useParams();
  const [form] = useForm();
  const auth = useAuth();

  const [availableGroups, setAvailableGroups] = useState<typeof Option[]>([]);
  const [availableOps, setAvailableOps] = useState<typeof Option[]>([]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);  

  useEffect(() => {
    let isMounted = true;
    async function initAvailableWmsOps () {
      const jsonApiResponse = await wmsOpRepo.findAll() as any;
      const wmsOps = jsonApiResponse.data.data.map((wmsOp: any) => 
        (<Option value={wmsOp.id} key={wmsOp.id}>{wmsOp.id}</Option>)
      );
      isMounted && setAvailableOps(wmsOps);
    }
    async function initAvailableGroups (userId: string) {
      const jsonApiResponse = await operation(
        // TODO fetch groups of user (not global groups)
        // 'List/api/v1/accounts/users/{parent_lookup_user}/groups/',
        'List/api/v1/accounts/groups/'
      ) as any;
      const groups = jsonApiResponse.data.data.map((group: any) => 
        (<Option value={group.id} key={group.id}>{group.attributes.name}</Option>)
      );
      isMounted && setAvailableGroups(groups);
    }
    async function initFromExistingRule (id: string) {
      const jsonApiResponse = await ruleRepo.get(id) as any;
      if (isMounted) {
        form.setFieldsValue({
          description: jsonApiResponse.data.data.attributes.description,
          area: jsonApiResponse.data.data.attributes['allowed_area'] 
            ? JSON.stringify(jsonApiResponse.data.data.attributes['allowed_area']) 
            : null,
          operations: jsonApiResponse.data.data.relationships.operations.data.map((operation: any) => operation.id ),
          groups: jsonApiResponse.data.data.relationships['allowed_groups'].data.map((group: any) => group.id )
        });
        const securedLayerIds = jsonApiResponse.data.data.relationships.secured_layers.data.map((layer: any) => 
          layer.id
        );
        setSelectedLayerIds(securedLayerIds);
      }
    }
    isMounted && initAvailableWmsOps();
    isMounted && auth && initAvailableGroups(auth.userId);
    isMounted && ruleId && initFromExistingRule(ruleId);
    return (() => { isMounted = false; });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[auth, ruleId]);

  const onFinish = (values: any) => {
    if (selectedLayerIds.length === 0) {
      setValidationErrors(['At least one layer needs to be selected.']);
      return;
    }
    async function create () {
      const createObj: WmsAllowedOperationCreate = {
        description: values.description,
        allowedArea: values.area,
        securedLayerIds: selectedLayerIds,
        allowedOperationIds: values.operations,
        allowedGroupIds: values.groups
      };      
      const res = await ruleRepo.create(createObj);
      if (res.status === 201) {
        notification.info({
          message: 'WMS security rule created',
          description: 'Your WMS security rule has been created'
        });
        navigate(`/registry/services/wms/${wmsId}/security`);
      }
    }
    async function update (ruleId: string) {
      const attributes:any = {
        description: values.description,
      };
      if (values.area) {
        attributes['allowed_area'] = values.area;
      } else {
        // TODO remove this workaround as soon as backend allows setting null values for deleting (optional) attributes
        attributes['allowed_area'] = 
          '{"type": "MultiPolygon", "coordinates": [[[[-180, -90], [-180, 90], [180, 90], [180, -90], [-180, -90]]]]}';
      }
      const relationships = {
        'secured_layers': {
          'data': selectedLayerIds.map((id) => {
            return {
              type: 'Layer',
              id: id
            };
          })
        },
        'operations': {
          'data': values.operations.map((id: any) => {
            return {
              type: 'WebMapServiceOperation',
              id: id
            };
          })
        },
        'allowed_groups': {
          'data': values.groups.map((id: any) => {
            return {
              type: 'Group',
              id: id
            };
          })
        }
      };
      const res = await ruleRepo.partialUpdate(ruleId, 'AllowedWebMapServiceOperation', attributes, relationships);
      if (res.status === 200) {
        notification.info({
          message: 'WMS security rule updated',
          description: 'Your WMS security rule has been updated'
        });
        navigate(`/registry/services/wms/${wmsId}/security`);
      }
    }    
    ruleId ? update(ruleId) : create();
  };

  return (
    <>
      <Form
        form={form}
        layout='vertical'
        onFinish={onFinish}
      >
        <InputField
          label='Description'
          name='description'
          placeholder='Short description of the security rule'
          validation={{
            rules: [{ required: true, message: 'Please input a description!' }],
            hasFeedback: false
          }}
        />
        <Form.Item 
          label='Groups'
          name='groups'
        >
          <Select
            mode='multiple'
            allowClear
            placeholder='Groups'
          >
            {availableGroups}
          </Select>
        </Form.Item>
        <Form.Item 
          label='Operations'
          name='operations'
          required={true}
          rules={[{ required: true, message: 'At least one operation must be selected!' }]}
        >
          <Select
            mode='multiple'
            allowClear
            placeholder='Allowed WMS operations'
          >
            {availableOps}
          </Select>
        </Form.Item>
        <Form.Item 
          label='Allowed area'
          name='area'
        >
          <TextArea />
        </Form.Item>                
        {
          validationErrors.map((error, i) => (
            <Form.Item key={i}>
              <Alert
                description={error}
                type='error'
              />
            </Form.Item>
          ))
        }
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
