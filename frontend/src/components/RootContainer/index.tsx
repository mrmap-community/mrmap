import { buildJsonApiPayload } from '@/utils/jsonapi';
import type { AxiosRequestConfig } from 'openapi-client-axios';
import { useEffect, useState } from 'react';
import { OpenAPIProvider } from 'react-openapi-client/OpenAPIProvider';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
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
    return await request('/api/schema/', { method: 'GET' });
  } catch (error) {}
};

const setDjangoLanguageCookie = () => {
  let lang;
  switch (getLocale()) {
    case 'de-DE':
      lang = 'de';
      break;
    case 'en-US':
    default:
      lang = 'en';
      break;
  }
  document.cookie = `django_language=${lang};path=/;SameSite=None;secure`;
};

const UserSettingsUpdater: React.FC = (props: any) => {
  const { initialState: { currentUser = undefined, settings = undefined } = {} } =
    useModel('@@initialState');
  const { isAuthenticated } = useAccess();
  const [updateUser, { error: updateUserError }] = useOperationMethod('updateUser');

  useEffect(() => {
    if (updateUserError) {
      console.log('can not update user settings');
    }
  }, [updateUserError]);

  useEffect(() => {
    if (currentUser && isAuthenticated) {
      updateUser(
        [{ name: 'id', value: currentUser.id, in: 'path' }],
        buildJsonApiPayload('User', currentUser.id, { settings: settings }),
      );
    }
  }, [settings, updateUser]);

  return props.children;
};



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
      <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig}>
        <UserSettingsUpdater>{props.children}</UserSettingsUpdater>
      </OpenAPIProvider>
    );
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
