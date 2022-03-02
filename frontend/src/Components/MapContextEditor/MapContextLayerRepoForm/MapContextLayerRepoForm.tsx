import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useForm } from 'antd/lib/form/Form';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import { AxiosResponse } from 'openapi-client-axios';
import { default as React, ReactElement, useCallback } from 'react';
import RepoForm from '../../Shared/RepoForm/RepoForm';

interface MapContextLayerRepoFormProps {
    layerGroup?: LayerGroup;
    selectedLayer?: BaseLayer;
}

export const MapContextLayerRepoForm = ({
  layerGroup,
  selectedLayer
}: MapContextLayerRepoFormProps
): ReactElement => {

  const [layerSettingsForm] = useForm();

  const onLayerSettingsChanged = useCallback((response: AxiosResponse) => {
    const layer: BaseLayer = MapUtil
      .getAllLayers(layerGroup)
      .filter((l: BaseLayer) => l.get('mapContextLayer').id === response.data.data.id)[0];
    layer.set('mapContextLayer', response.data.data);
  }, [layerGroup]);

  return (
    <RepoForm
      resourceType='MapContextLayer'
      resourceId={selectedLayer && selectedLayer.get('mapContextLayer').id}
      form={layerSettingsForm}
      onSuccess={onLayerSettingsChanged}
    />
  );
};
