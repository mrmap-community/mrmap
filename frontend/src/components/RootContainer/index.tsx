import { PageLoading } from "@ant-design/pro-layout";
import type { AxiosRequestConfig } from "openapi-client-axios";
import { useEffect, useState } from "react";
import { OpenAPIProvider } from "react-openapi-client";
import { request } from 'umi';

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
      return await request('/api/schema/', {method: 'GET'});
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
        }
        fetchSchemaAsync();
    }, []);

    if (schema){
        console.log('root', schema);
        return (
            <OpenAPIProvider definition={schema} axiosConfigDefaults={axiosConfig} >
                {props.children}
            </OpenAPIProvider>
        );
    }
    return (          
        <PageLoading />
    );


};


export default RootContainer;