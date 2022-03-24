import type { ReactElement } from 'react';
import { useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { history, useModel } from 'umi';

const loginPath = '/user/login';

const InitializeUmi = (props: any): ReactElement => {
    
  const {setInitialState} = useModel('@@initialState');
  
  const [
    getCurrentUser, 
    { loading, error, response }
  ] = useOperationMethod('getCurrentUser');

  useEffect(() => {
    if (!response){
      getCurrentUser();
    } else if (!loading && !error) {
      setInitialState((s: any) => ({
        ...s,
        currentUser: response.data
      }));
      if (history.location.pathname !== loginPath) {
        /** Redirect to the page specified by redirect parameter */
        const { query } = history.location;
        const { redirect } = query as { redirect: string };
        setTimeout(() => {
          history.push(redirect || '/');
        });
      }
    }

    if (error) {
      setTimeout(() => {
        history.push(loginPath);

      });
    }
  }, [error, getCurrentUser, loading, response, setInitialState]);


  return props.children
};

export default InitializeUmi;