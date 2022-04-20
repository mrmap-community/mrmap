import { InputField } from '@/components/InputField';
import { screenToWgs84, wgs84ToScreen, zoomTo } from '@/utils/map';
import { useMap } from '@terrestris/react-geo';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { Alert, Button, Form, Select, Space, Spin } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { Feature } from 'ol';
import GeoJSON from 'ol/format/GeoJSON';
import type OlGeometry from 'ol/geom/Geometry';
import MultiPolygon from 'ol/geom/MultiPolygon';
import Polygon from 'ol/geom/Polygon';
import type OlVectorLayer from 'ol/layer/Vector';
import type OlVectorSource from 'ol/source/Vector';
import type { ReactElement } from 'react';
import { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { FormattedMessage, history, useIntl } from 'umi';
import AllowedAreaTable from '../AllowedAreaTable';

const { Option } = Select;

const geoJson = new GeoJSON();

interface RuleFormProps {
  wmsId: string;
  selectedLayerIds: string[];
  setSelectedLayerIds: (ids: string[]) => void;
  setIsRuleEditingActive: (isActive: boolean) => void;
}

const RuleForm = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds,
  setIsRuleEditingActive,
}: RuleFormProps): ReactElement => {
  const map = useMap();
  const [form] = useForm();
  const { ruleId } = useParams<{ ruleId: string }>();
  const intl = useIntl();

  const [digiLayer, setDigiLayer] = useState<OlVectorLayer<OlVectorSource<OlGeometry>>>();
  const [availableGroups, setAvailableGroups] = useState<typeof Option[]>([]);
  const [availableOps, setAvailableOps] = useState<typeof Option[]>([]);
  const [layerSelectionError, setLayerSelectionError] = useState<string>();

  const [listWmsOps, { response: listWmsOpsRes, loading: listWmsOpsLoading }] = useOperationMethod(
    'listWebMapServiceOperation',
  );
  const [getAllowedWmsOp, { response: getAllowedWmsOpRes, loading: getAllowedWmsOpLoading }] =
    useOperationMethod('getAllowedWebMapServiceOperation');
  const [addAllowedWmsOp, { response: addAllowedWmsOpRes, loading: addAllowedWmsOpLoading }] =
    useOperationMethod('addAllowedWebMapServiceOperation');
  const [
    updateAllowedWmsOp,
    { response: updateAllowedWmsOpRes, loading: updateAllowedWmsOpLoading },
  ] = useOperationMethod('updateAllowedWebMapServiceOperation');

  // map becomes available -> get digi layer
  useEffect(() => {
    if (map) {
      const layer = DigitizeUtil.getDigitizeLayer(map);
      setDigiLayer(layer);
      return () => {
        layer.getSource()?.clear();
      };
    }
    return undefined;
  }, [map, digiLayer]);

  // mount -> rule editing mode is set active
  useEffect(() => {
    setIsRuleEditingActive(true);
    return () => {
      // when unmounting, rule editing mode becomes inactive
      setIsRuleEditingActive(false);
    };
  }, [setIsRuleEditingActive]);

  // mount -> request WMS ops
  useEffect(() => {
    listWmsOps();
  }, [listWmsOps]);

  // wmsId -> request allowed WMS op (rule)
  useEffect(() => {
    if (ruleId) {
      getAllowedWmsOp([
        {
          name: 'id',
          value: ruleId,
          in: 'path',
        },
      ]);
    }
  }, [getAllowedWmsOp, ruleId]);

  // WMS ops response -> init WMS ops dropdown
  useEffect(() => {
    if (listWmsOpsRes) {
      const wmsOps = listWmsOpsRes.data.data.map((wmsOp: any) => (
        <Option value={wmsOp.id} key={wmsOp.id}>
          {wmsOp.id}
        </Option>
      ));
      // TODO ensure not setting if component unmounted
      setAvailableOps(wmsOps);
    }
  }, [listWmsOpsRes]);

  // allowed WMS ops response
  useEffect(() => {
    if (map && digiLayer && getAllowedWmsOpRes) {
      const attrs = getAllowedWmsOpRes.data.data.attributes;
      const rels = getAllowedWmsOpRes.data.data.relationships;
      // set form fields
      form.setFieldsValue({
        description: attrs.description,
        operations: rels.operations.data.map((o: any) => o.id),
        groups: rels.allowedGroups.data.map((o: any) => o.id),
      });
      // set layers
      setSelectedLayerIds(rels.securedLayers.data.map((o: any) => o.id));
      // set area polygons and zoom map
      if (attrs.allowedArea) {
        const geom: any = geoJson.readGeometry(attrs.allowedArea);
        geom.getPolygons().forEach((polygon: Polygon) => {
          const feature = new Feature({
            geometry: wgs84ToScreen(polygon),
          });
          digiLayer.getSource()?.addFeature(feature);
        });
        zoomTo(map, wgs84ToScreen(geom));
      }
    }
  }, [form, digiLayer, map, setSelectedLayerIds, getAllowedWmsOpRes]);

  // add allowed WMS ops response
  useEffect(() => {
    if (addAllowedWmsOpRes) {
      // TODO check for 201 (CREATED)?
      history.push(`/registry/wms/${wmsId}/security`);
    }
  }, [addAllowedWmsOpRes, wmsId]);

  // update allowed WMS ops response
  useEffect(() => {
    if (updateAllowedWmsOpRes) {
      // TODO check for 200 (OK)?
      history.push(`/registry/wms/${wmsId}/security`);
    }
  }, [updateAllowedWmsOpRes, wmsId]);

  // get map digitize layer, fetch form data and initialize
  useEffect(() => {
    let isMounted = true;
    async function initAvailableGroups() {
      // TODO wait for backend fix and reactivate fetching below
      // const jsonApiResponse = await operation('List/api/v1/accounts/groups/');
      // const groups = jsonApiResponse.data.data.map((group: any) =>
      //   (<Option value={group.id} key={group.id}>{group.attributes.name}</Option>)
      // );
      const groups: any = [
        <Option value="1" key="1">
          Testorganisation
        </Option>,
      ];
      if (isMounted) {
        setAvailableGroups(groups);
      }
    }
    if (map) {
      initAvailableGroups();
    }
    return () => {
      isMounted = false;
      digiLayer?.getSource()?.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, form]);

  const onFinish = async (values: any) => {
    if (selectedLayerIds.length === 0) {
      setLayerSelectionError(
        intl.formatMessage({
          id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.layerRequired',
          defaultMessage: 'Please select at least one layer.',
        }),
      );
      return;
    }
    setLayerSelectionError(undefined);

    // get GeoJson geometry from digitizing layer
    let allowedAreaGeoJson: string | null = null;
    const coords: any[] = [];
    digiLayer
      ?.getSource()
      ?.getFeatures()
      .forEach((feature) => {
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
      allowedArea: allowedAreaGeoJson,
    };
    const relationships: any = {
      securedService: {
        data: {
          type: 'WebMapService',
          id: wmsId,
        },
      },
      securedLayers: {
        data: selectedLayerIds.map((layerId) => {
          return {
            type: 'Layer',
            id: layerId,
          };
        }),
      },
      operations: {
        data: values.operations.map((opId: any) => {
          return {
            type: 'WebMapServiceOperation',
            id: opId,
          };
        }),
      },
    };
    if (values.groups) {
      relationships.allowedGroups = {
        data: values.groups.map((groupId: any) => {
          return {
            type: 'Group',
            id: groupId,
          };
        }),
      };
    }

    // perform create or partial update operation
    try {
      if (ruleId) {
        updateAllowedWmsOp(
          [
            {
              in: 'path',
              name: 'id',
              value: ruleId,
            },
          ],
          {
            data: {
              type: 'AllowedWebMapServiceOperation',
              id: ruleId,
              attributes,
              relationships,
            },
          },
        );
        // if (response.status !== 200) {
        //   notification.error({ message: 'Unexpected response code' });
        //   return;
        // }
      } else {
        addAllowedWmsOp([], {
          data: {
            type: 'AllowedWebMapServiceOperation',
            attributes,
            relationships,
          },
        });
        // if (response.status !== 201) {
        //   notification.error({ message: 'Unexpected response code' });
        //   return;
        // }
      }
    } finally {
    }
  };

  const isSavingOrLoading =
    listWmsOpsLoading ||
    getAllowedWmsOpLoading ||
    addAllowedWmsOpLoading ||
    updateAllowedWmsOpLoading;

  return (
    <Spin spinning={isSavingOrLoading}>
      <Form form={form} layout="vertical" onFinish={onFinish}>
        <InputField
          name="description"
          label={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.descriptionLabel',
            defaultMessage: 'Description',
          })}
          placeholder={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.descriptionPlaceholder',
            defaultMessage: 'Short description of the security rule',
          })}
          validation={{
            rules: [
              {
                required: true,
                message: intl.formatMessage({
                  id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.descriptionRequired',
                  defaultMessage: 'Please input a description.',
                }),
              },
            ],
            hasFeedback: false,
          }}
        />
        <Form.Item
          name="groups"
          label={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.groupsLabel',
            defaultMessage: 'Groups',
          })}
        >
          <Select
            mode="multiple"
            allowClear
            placeholder={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.groupsLabel',
              defaultMessage: 'Groups',
            })}
          >
            {availableGroups}
          </Select>
        </Form.Item>
        <Form.Item
          name="operations"
          label={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.operationsLabel',
            defaultMessage: 'Operations',
          })}
          required={true}
          rules={[
            {
              required: true,
              message: intl.formatMessage({
                id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.operationsRequired',
                defaultMessage: 'Please select at least one operation.',
              }),
            },
          ]}
        >
          <Select
            mode="multiple"
            allowClear
            placeholder={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.allowedWmsOperationsPlaceholder',
              defaultMessage: 'Allowed WMS operations',
            })}
          >
            {availableOps}
          </Select>
        </Form.Item>
        <Form.Item
          name="area"
          label={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.rulesDrawer.ruleForm.allowedAreaLabel',
            defaultMessage: 'Allowed area',
          })}
        >
          <AllowedAreaTable />
        </Form.Item>
        {layerSelectionError && (
          <Form.Item key="layerSelectionError">
            <Alert description={layerSelectionError} type="error" />
          </Form.Item>
        )}
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              <FormattedMessage
                id="pages.wmsSecuritySettings.rulesDrawer.ruleForm.save"
                defaultMessage="Save"
              />
            </Button>
            <Button
              htmlType="button"
              onClick={() => history.push(`/registry/wms/${wmsId}/security`)}
            >
              <FormattedMessage
                id="pages.wmsSecuritySettings.rulesDrawer.ruleForm.cancel"
                defaultMessage="Cancel"
              />
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </Spin>
  );
};

export default RuleForm;
