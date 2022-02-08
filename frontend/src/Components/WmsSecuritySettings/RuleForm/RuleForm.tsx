import { useMap } from '@terrestris/react-geo';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { Alert, Button, Form, notification, Select, Space } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { Feature } from 'ol';
import GeoJSON from 'ol/format/GeoJSON';
import OlGeometry from 'ol/geom/Geometry';
import MultiPolygon from 'ol/geom/MultiPolygon';
import Polygon from 'ol/geom/Polygon';
import OlVectorLayer from 'ol/layer/Vector';
import OlVectorSource from 'ol/source/Vector';
import { default as React, ReactElement, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../../Hooks/useAuth';
import { operation } from '../../../Repos/JsonApi';
import WmsAllowedOperationRepo, { WmsAllowedOperationCreate } from '../../../Repos/WmsAllowedOperationRepo';
import WmsOperationRepo from '../../../Repos/WmsOperationRepo';
import { InputField } from '../../Shared/FormFields/InputField/InputField';
import { AllowedAreaList } from './AllowedAreaList';

const { Option } = Select;

const wmsOpRepo = new WmsOperationRepo();
const geoJson = new GeoJSON();

interface RuleFormProps {
    wmsId: string,
    selectedLayerIds: string[],
    setSelectedLayerIds: (ids: string[]) => void
    setIsRuleEditingActive: (isActive: boolean) => void    
}

export const RuleForm = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds,
  setIsRuleEditingActive  
}: RuleFormProps): ReactElement => {

  setIsRuleEditingActive(true);

  const ruleRepo = new WmsAllowedOperationRepo(wmsId);

  const navigate = useNavigate();
  const { ruleId } = useParams();
  const [form] = useForm();
  const auth = useAuth();
  const map = useMap();

  const [layer, setLayer] = useState<OlVectorLayer<OlVectorSource<OlGeometry>>>();  
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
        if (jsonApiResponse.data.data.attributes['allowed_area']) {
          console.log ('Reading', jsonApiResponse.data.data.attributes['allowed_area']);
          const geom: any = geoJson.readGeometry(
            jsonApiResponse.data.data.attributes['allowed_area']
          );
          geom.getPolygons().forEach( (polygon:Polygon) => {
            const feature = new Feature ( {
              geometry: polygon.clone().transform('EPSG:4326', 'EPSG:900913')
            });
            layer?.getSource().addFeature(feature);
          });
          const nativeGeom = geom.clone().transform('EPSG:4326', 'EPSG:900913');
          map.getView().fit(nativeGeom.getExtent());
        }
      }
    }
    setLayer(DigitizeUtil.getDigitizeLayer(map));
    isMounted && initAvailableWmsOps();
    isMounted && auth && initAvailableGroups(auth.userId);
    isMounted && ruleId && layer && initFromExistingRule(ruleId);
    return (() => { 
      isMounted = false;
      layer?.getSource().clear();
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[auth, ruleId, map, layer]);

  const onFinish = (values: any) => {
    if (selectedLayerIds.length === 0) {
      setValidationErrors(['At least one layer needs to be selected.']);
      return;
    }
    
    let allowedAreaGeoJson: string|null = null;
    const coords: any [] = [];
    layer?.getSource().getFeatures().forEach ((feature) => {
      const poly:any = feature.getGeometry()?.clone().transform('EPSG:900913', 'EPSG:4326');
      coords.push(poly.getCoordinates());
    });
    if (coords.length > 0) {
      const multiPoly = new MultiPolygon(coords);
      allowedAreaGeoJson = geoJson.writeGeometry(multiPoly);      
    }
    async function create () {
      const createObj: WmsAllowedOperationCreate = {
        description: values.description,
        allowedArea: allowedAreaGeoJson,
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
        'allowed_area': allowedAreaGeoJson
      };
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
          <AllowedAreaList />
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
