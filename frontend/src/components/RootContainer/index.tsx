import { store } from '@/services/ReduxStore/Store';
import { buildJsonApiPayload } from '@/utils/jsonapi';
import { olMap } from '@/utils/map';
import { MapContext } from '@terrestris/react-geo';
import type { AxiosRequestConfig } from 'openapi-client-axios';
import { useEffect, useState } from 'react';
import { OpenAPIProvider } from 'react-openapi-client/OpenAPIProvider';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { Provider as ReduxProvider } from 'react-redux';
import { getLocale, request, useIntl, useModel } from 'umi';
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
    return await request('/api/schema/', { method: 'GET'});
  } catch (error) {
  }
};

const setDjangoLanguageCookie = () => {
  let lang;
  switch(getLocale()){
    case 'de-DE':
      lang = 'de';
      break;
    case 'en-US':
    default:
      lang = 'en';
      break;
  }
  document.cookie = `django_language=${lang};path=/`;
};


const UserSettingsHandler: React.FC = (props: any) => {
  const { initialState, setInitialState } = useModel('@@initialState');

  const [updateUser, { response: updateUserResponse }] = useOperationMethod('updateUser');

  useEffect(() => {
    if (updateUserResponse && updateUserResponse.status === 200){
      setInitialState((s: any) => ({
        ...s,
        currentUser: updateUserResponse.data
      }));
    }
    
  }, [setInitialState, updateUserResponse]);

  useEffect(() => {
    if (initialState?.currentUser){
      console.log('initial state updated', initialState);
      updateUser(
        [{ name: 'id', value: initialState.currentUser.id, in: 'path' }],
        buildJsonApiPayload('User', initialState.currentUser.id, { settings: initialState.settings })
      );
    }
  }, [initialState, updateUser]);
  
  return (props.children);
}

/**
 * Workaround to init openapi provider before child containers are rendered
 * TODO: check if this can be simplyfied
 */
const RootContainer: React.FC = (props: any) => {
  const intl = useIntl();
  const [schema, setSchema] = useState();

  useEffect(() => {
    setDjangoLanguageCookie();
    
    const fetchSchemaAsync = async () => {
      setSchema(await fetchSchema());
    };
    fetchSchemaAsync();
  }, []);

  if (schema) {
    return (
      <ReduxProvider store={store}>
        <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig}>
          <UserSettingsHandler>
            <MapContext.Provider value={olMap}>{props.children}</MapContext.Provider>
          </UserSettingsHandler>
        </OpenAPIProvider>
      </ReduxProvider>
    );
  }
  return (
    <PageLoading
      title={intl.formatMessage({ id: 'component.rootContainer.loadingSchema' })}
      logo={<img alt="openapi logo" src="/openapi_logo.png" />}
    />
  );
};

export default RootContainer;
