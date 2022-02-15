import { useMap } from '@terrestris/react-geo';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { Alert, Button, Form, notification, Select, Space, Spin } from 'antd';
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
import { createOrUpdate, operation } from '../../../../Repos/JsonApi';
import { screenToWgs84, wgs84ToScreen, zoomTo } from '../../../../Utils/MapUtils';
import { InputField } from '../../../Shared/FormFields/InputField/InputField';
import { AllowedAreaTable } from './AllowedAreaTable/AllowedAreaTable';

const { Option } = Select;

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

  const navigate = useNavigate();
  const { ruleId } = useParams();
  const [form] = useForm();
  const map = useMap();

  const [layer, setLayer] = useState<OlVectorLayer<OlVectorSource<OlGeometry>>>();  
  const [availableGroups, setAvailableGroups] = useState<typeof Option[]>([]);
  const [availableOps, setAvailableOps] = useState<typeof Option[]>([]);
  const [layerSelectionError, setLayerSelectionError] = useState<string>();
  const [isSavingOrLoading, setIsSavingOrLoading] = useState(false);

  // after mount, rule editing mode is active
  useEffect(() => {
    setIsRuleEditingActive(true);
    return ( () => {
      // when unmounting, rule editing mode becomes inactive
      setIsRuleEditingActive(false);
    });
  },[setIsRuleEditingActive]);

  // get map digitize layer, fetch form data and initialize
  useEffect(() => {
    let isMounted = true;
    let digiLayer: OlVectorLayer<OlVectorSource<OlGeometry>>;
    async function initAvailableWmsOps () {
      const jsonApiResponse = await operation('listAllowedWebMapServiceOperation');
      const wmsOps = jsonApiResponse.data.data.map((wmsOp: any) => 
        (<Option value={wmsOp.id} key={wmsOp.id}>{wmsOp.id}</Option>)
      );
      isMounted && setAvailableOps(wmsOps);
    }
    async function initAvailableGroups () {
      // TODO wait for backend fix and reactivate fetching below
      // const jsonApiResponse = await operation('List/api/v1/accounts/groups/');
      // const groups = jsonApiResponse.data.data.map((group: any) => 
      //   (<Option value={group.id} key={group.id}>{group.attributes.name}</Option>)
      // );
      const groups: any = [<Option value='1' key='1'>Testorganisation</Option>];
      isMounted && setAvailableGroups(groups);
    }
    async function initFromExistingRule (id: string) {
      const jsonApiResponse = await operation(
        'getAllowedWebMapServiceOperation',
        [{
          in: 'path',
          name: 'id',
          value: String(id),
        }]
      );
      if (isMounted) {
        const attrs = jsonApiResponse.data.data.attributes;
        const rels = jsonApiResponse.data.data.relationships;
        // set form fields
        form.setFieldsValue({
          description: attrs.description,
          operations: rels.operations.data.map((o: any) => o.id),
          groups: rels.allowedGroups.data.map((o: any) => o.id)
        });
        // set layers
        setSelectedLayerIds(rels.securedLayers.data.map((o: any) => o.id));
        // set area polygons and zoom map
        if (attrs.allowedArea) {
          const geom: any = geoJson.readGeometry(attrs.allowedArea);
          geom.getPolygons().forEach((polygon: Polygon) => {
            const feature = new Feature ( {
              geometry: wgs84ToScreen(polygon)
            });
            digiLayer?.getSource().addFeature(feature);
          });
          zoomTo(map, wgs84ToScreen(geom));
        }
      }
    }
    if (map) {
      setIsSavingOrLoading(true);
      digiLayer = DigitizeUtil.getDigitizeLayer(map);
      setLayer(digiLayer);
      initAvailableWmsOps();
      initAvailableGroups();
      ruleId && initFromExistingRule(ruleId);
      setIsSavingOrLoading(false);
    }
    return (() => {
      isMounted = false;
      digiLayer?.getSource().clear();
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[ruleId, map, form]);

  const onFinish = async (values: any) => {
    if (selectedLayerIds.length === 0) {
      setLayerSelectionError('At least one layer needs to be selected.');
      return;
    }
    setLayerSelectionError(undefined);

    // get GeoJson geometry from digitizing layer
    let allowedAreaGeoJson: string|null = null;
    const coords: any [] = [];
    layer?.getSource().getFeatures().forEach ((feature) => {
      const geom = feature.getGeometry();
      if (geom) {
        const wgs84Geom = screenToWgs84(geom);
        if (wgs84Geom instanceof Polygon) {
          coords.push((wgs84Geom as Polygon).getCoordinates());
        }
      }
    });
    if (coords.length > 0) {
      const multiPoly = new MultiPolygon(coords);
      allowedAreaGeoJson = geoJson.writeGeometry(multiPoly);      
    }

    // build attributes and relationships
    const attributes = {
      description: values.description,
      allowedArea: allowedAreaGeoJson
    };
    const relationships: any = {
      securedService: {
        data: {
          type: 'WebMapService',
          id: wmsId
        }
      },
      securedLayers: {
        data: selectedLayerIds.map((id) => {
          return {
            type: 'Layer',
            id: id
          };
        })
      },
      operations: {
        data: values.operations.map((id: any) => {
          return {
            type: 'WebMapServiceOperation',
            id: id
          };
        })
      }
    };
    if (values.groups) {
      relationships.allowedGroups = {
        data: values.groups.map((id: any) => {
          return {
            type: 'Group',
            id: id
          };
        })
      };
    }

    // perform create or partial update operation
    try {
      setIsSavingOrLoading(true);
      if (ruleId) {
        const response = await createOrUpdate(
          'updateAllowedWebMapServiceOperation',
          'AllowedWebMapServiceOperation',
          attributes,
          relationships,
          [{
            in: 'path',
            name: 'id',
            value: ruleId
          }],
          ruleId
        );
        if (response.status !== 200) {
          notification.error({ message: 'Unexpected response code' });
          return;
        }
      } else {
        const response = await createOrUpdate(
          'addAllowedWebMapServiceOperation',
          'AllowedWebMapServiceOperation',
          attributes,
          relationships
        );
        if (response.status !== 201) {
          notification.error({ message: 'Unexpected response code' });
          return;
        }
      }
    } finally {
      setIsSavingOrLoading(false);
    }
    navigate(`/registry/services/wms/${wmsId}/security`);
  };

  return (
    <Spin spinning={isSavingOrLoading}>
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
          <AllowedAreaTable />
        </Form.Item>        
        {
          layerSelectionError &&
          <Form.Item key='layerSelectionError'>
            <Alert
              description={layerSelectionError}
              type='error'
            />
          </Form.Item>
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
    </Spin>
  );
};
