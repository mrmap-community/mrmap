import { useForm } from 'antd/lib/form/Form';
import { default as React, ReactElement, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useNavigate } from 'react-router-dom';
import { JsonApiPrimaryData } from '../../../Repos/JsonApiRepo';
import RepoForm from '../../Shared/RepoForm/RepoForm';

export const MapContextSettings = ({
  id
}: {
  id:string|undefined
}
): ReactElement => {

  const [form] = useForm();
  const navigate = useNavigate();

  const [
    addMapContextLayer,
    {
      response: addMapContextLayerResponse,
      // error: addMapContextLayerError //TODO
    }
  ] = useOperationMethod('addMapContextLayer');

  useEffect( () => {
    if (navigate && addMapContextLayerResponse) {
      const mapContextId = addMapContextLayerResponse.data.data.relationships.mapContext.data.id;
      navigate(`/registry/mapcontexts/${mapContextId}/edit`);
    }
  }, [navigate, addMapContextLayerResponse]);

  return (
    <RepoForm
      resourceType='MapContext'
      resourceId={id}
      form={form}
      onSuccess={(response, created) => {
        if (created) {
          const mapContextId = (response.data.data as JsonApiPrimaryData).id;
          const relationships: any = {
            mapContext: {
              data: {
                type: 'MapContext',
                id: mapContextId
              }
            }
          };
          addMapContextLayer([], {
            data: {
              type: 'MapContextLayer',
              attributes: {
                title: 'root'
              },
              relationships: {
                ...relationships
              }
            }
          });
          navigate(`/registry/mapcontexts/${mapContextId}/edit`);
        }
      }}
    />
  );
};
