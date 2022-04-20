import SchemaForm from '@/components/SchemaForm';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useForm } from 'antd/lib/form/Form';
import type BaseLayer from 'ol/layer/Base';
import type LayerGroup from 'ol/layer/Group';
import type { AxiosResponse } from 'openapi-client-axios';
import type { ReactElement } from 'react';
import { useCallback } from 'react';

interface MapContextLayerRepoFormProps {
  layerGroup?: LayerGroup;
  selectedLayer?: BaseLayer;
}

const MapContextLayerRepoForm = ({
  layerGroup,
  selectedLayer,
}: MapContextLayerRepoFormProps): ReactElement => {
  const [layerSettingsForm] = useForm();

  const onLayerSettingsChanged = useCallback(
    (response: AxiosResponse) => {
      if (layerGroup) {
        const layer: BaseLayer = MapUtil.getAllLayers(layerGroup).filter(
          (l: BaseLayer) => l.get('mapContextLayer').id === response.data.data.id,
        )[0];
        layer.set('mapContextLayer', response.data.data);
      }
    },
    [layerGroup],
  );

  return (
    <SchemaForm
      resourceType="MapContextLayer"
      resourceId={selectedLayer && selectedLayer.get('mapContextLayer').id}
      form={layerSettingsForm}
      onSuccess={onLayerSettingsChanged}
    />
  );
};

export default MapContextLayerRepoForm;
