import { store } from '@/services/ReduxStore/Store';
import WebSockets from '@/services/WebSockets';
import { buildJsonApiPayload } from '@/utils/jsonapi';
import { olMap } from '@/utils/map';
import { MapContext } from '@terrestris/react-geo';
import type { AxiosRequestConfig } from 'openapi-client-axios';
import { useEffect, useState } from 'react';
import { OpenAPIProvider } from 'react-openapi-client/OpenAPIProvider';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { Provider as ReduxProvider } from 'react-redux';
import { getLocale, request, useAccess, useIntl, useModel } from 'umi';
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
  const { initialState: { currentUser = undefined, settings = undefined } = {}, setInitialState } = useModel('@@initialState');

  const [updateUser, { response: updateUserResponse }] = useOperationMethod('updateUser');

  useEffect(() => {
    if (updateUserResponse && updateUserResponse.status === 200){
      setInitialState((s: any) => ({
        ...s,
        userInfoResponse: updateUserResponse,
        currentUser: updateUserResponse.data.data,
      }));
    }
    
  }, [setInitialState, updateUserResponse]);

  useEffect(() => {
    //FIXME: currently this will result in an initial patch, cause settings are set on getInitialState function...
    if (currentUser){
      console.log('current user', currentUser);
      updateUser(
        [{ name: 'id', value: currentUser.id, in: 'path' }],
        buildJsonApiPayload('User', currentUser.id, { settings: settings })
      );
    }
  }, [settings, updateUser]);
  
  return (props.children);
}

/**
 * Workaround to init openapi provider before child containers are rendered
 * TODO: check if this can be simplyfied
 */
const RootContainer: React.FC = (props: any) => {
  const intl = useIntl();
  const [schema, setSchema] = useState();
  const { isAuthenticated } = useAccess();

  useEffect(() => {
    setDjangoLanguageCookie();
    
    const fetchSchemaAsync = async () => {
      setSchema(await fetchSchema());
    };
    fetchSchemaAsync();
  }, []);

  if (schema) {
    if (isAuthenticated){
      return (
        <ReduxProvider store={store}>
          <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig}>
            <UserSettingsHandler>
              <WebSockets>
                <MapContext.Provider value={olMap}>{props.children}</MapContext.Provider>
              </WebSockets>
            </UserSettingsHandler>
          </OpenAPIProvider>
        </ReduxProvider>
      );
    }else {
      return (
        <ReduxProvider store={store}>
          <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig}>
            <UserSettingsHandler>
              {props.children}
            </UserSettingsHandler>
          </OpenAPIProvider>
        </ReduxProvider>
      );
    }
    
  } else {
    return (
      <PageLoading
        title={intl.formatMessage({ id: 'component.rootContainer.loadingSchema' })}
        logo={<img alt="openapi logo" src="/openapi_logo.png" />}
      />
    );
  }
};

export default RootContainer;
