import { useMap } from '@terrestris/react-geo';
import React, { ReactElement, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { LeftDrawer } from '../Shared/LeftDrawer/LeftDrawer';
import './MapContextEditor.css';

export const MapContextEditor = (): ReactElement => {

  const { id } = useParams();
  const map = useMap();

  const [
    getMapContext,
    {
      loading: getMapContextLoading,
      response: getMapContextResponse
    }
  ] = useOperationMethod('getMapContext');

  // init: request map context and related data (map context layers, rendering layer, operation urls)
  useEffect(() => {
    if (id) {
      getMapContext([
        { name: 'id', value: String(id), in: 'path' },
        { name: 'include', value: 'mapContextLayers.renderingLayer.service.operationUrls', in: 'query' }
      ]);
    }
  }, [getMapContext, id]);

  // init: handle map context response: build layer tree
  useEffect(() => {
    if (getMapContextResponse) {
      console.log('response', getMapContextResponse);
    }
  }, [getMapContextResponse]);

  return (
    <>
      <div className='mapcontext-editor-layout'>
        <LeftDrawer map={map}>
          <h1>LayerTree</h1>
        </LeftDrawer>
        <AutoResizeMapComponent id='map' />
      </div>
    </>
  );
};
