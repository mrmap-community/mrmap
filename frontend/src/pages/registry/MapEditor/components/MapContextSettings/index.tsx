import SchemaForm from '@/components/SchemaForm';
import type { JsonApiPrimaryData } from '@/utils/jsonapi';
import { useForm } from 'antd/lib/form/Form';
import type { ReactElement } from 'react';
import { useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { history } from 'umi';

const MapContextSettings = ({ id }: { id: string | undefined }): ReactElement => {
  const [form] = useForm();

  const [
    addMapContextLayer,
    {
      response: addMapContextLayerResponse,
      // error: addMapContextLayerError //TODO
    },
  ] = useOperationMethod('addMapContextLayer');

  useEffect(() => {
    if (addMapContextLayerResponse) {
      const mapContextId = addMapContextLayerResponse.data.data.relationships.mapContext.data.id;
      history.push(`/registry/maps/${mapContextId}/edit`);
    }
  }, [addMapContextLayerResponse]);

  return (
    <SchemaForm
      resourceType="MapContext"
      resourceId={id}
      form={form}
      onSuccess={(response, created) => {
        if (created) {
          const mapContextId = (response.data.data as JsonApiPrimaryData).id;
          const relationships: any = {
            mapContext: {
              data: {
                type: 'MapContext',
                id: mapContextId,
              },
            },
          };
          addMapContextLayer([], {
            data: {
              type: 'MapContextLayer',
              attributes: {
                title: 'root',
              },
              relationships: {
                ...relationships,
              },
            },
          });
          history.push(`/registry/maps/${mapContextId}/edit`);
        }
      }}
    />
  );
};

export default MapContextSettings;
