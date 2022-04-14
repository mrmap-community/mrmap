import StoreProvider from '@/services/ReduxStore/Store';
import { olMap } from '@/utils/map';
import { MapContext } from '@terrestris/react-geo';
import type { AxiosRequestConfig } from 'openapi-client-axios';
import { useEffect, useState } from 'react';
import { OpenAPIProvider } from 'react-openapi-client';
import { request } from 'umi';
import PageLoading from '../PageLoading';

const axiosConfig: AxiosRequestConfig = {
  baseURL: '/',
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/vnd.api+json',
  },
};

const fetchSchema = async () => {
  try {
    return await request('/api/schema/', { method: 'GET' });
  } catch (error) {
    console.log('can not load schema');
  }
};



/**
 * Workaround to init openapi provider before child containers are rendered
 * TODO: check if this can be simplyfied
 */
const RootContainer: React.FC = (props: any) => {
  const [schema, setSchema] = useState();

  useEffect(() => {
    const fetchSchemaAsync = async () => {
      setSchema(await fetchSchema());
    };
    fetchSchemaAsync();
  }, []);

  if (schema) {
    return (
      <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig}>
        <StoreProvider>
          <MapContext.Provider value={olMap}>{props.children}</MapContext.Provider>
        </StoreProvider>
      </OpenAPIProvider>
    );
  }
  return (
    <PageLoading
      title="Loading OpenAPI schema from backend..."
      logo={<img alt="openapi logo" src="/openapi_logo.png" />}
    />
  );
};

export default RootContainer;
