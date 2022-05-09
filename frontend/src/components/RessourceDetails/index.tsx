import type { JsonApiDocument, JsonApiPrimaryData } from "@/utils/jsonapi";
import { PageContainer } from "@ant-design/pro-layout";
import type { AxiosError, ParamsArray } from "openapi-client-axios";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { useOperationMethod } from "react-openapi-client/useOperationMethod";
import { history, useIntl, useParams } from 'umi';

export interface RessourceDetailsProps {
    children?: ReactNode | undefined
    onRessourceResponse?: (ressource: JsonApiDocument) => void;
    resourceType: string;
    additionalGetRessourceParams?: ParamsArray;
    rebuild?: boolean;
}

const RessourceDetails = ({
    children = undefined,
    onRessourceResponse = undefined,
    resourceType,
    additionalGetRessourceParams = [],
    rebuild = false,
}: RessourceDetailsProps): ReactElement => {

    /**
     * page hooks
     */
    const intl = useIntl();
    const { id } = useParams<{ id: string }>();
    const [ loading, setLoading ] = useState(true);
    const [ isInitialized, setIsInitialized ] = useState(false);

    /**
     * Api hooks
     */
     const [
        getRessource, 
        { loading: isRessourceLoading, response: getRessourceResponse, error: getRessourceError }
    ] = useOperationMethod(`get${resourceType}`);    
    
    /**
     * derived constants
     */
    const getResourceAxiosError = getRessourceError as AxiosError;
    const jsonApiResponse: JsonApiDocument = getRessourceResponse?.data;
    const ressource: JsonApiPrimaryData = getRessourceResponse?.data?.data;

    const getRessourceParams = useCallback((): ParamsArray => {return [
        ...additionalGetRessourceParams,
        {
            in: 'path',
            name: 'id',
            value: String(id),
        }
    ]}, [additionalGetRessourceParams, id]);

    /**
     * @description hook to receive the resource on initial
     */
    useEffect(() => {
        if (!isRessourceLoading && !isInitialized || !isRessourceLoading && rebuild){
            getRessource(getRessourceParams());
        }
    }, [getRessource, getRessourceParams, isInitialized, isRessourceLoading, rebuild]);


    /**
     * @description Redirect if requested ressource could'nt be founded
     */
     useEffect(() => {
        if (getResourceAxiosError?.response?.status === 404){
            history.push('/404');
        }
    }, [getResourceAxiosError]);

    /**
     * @description If we responses a ressource the passed in onRessourceResponse function will be triggered
     */
    useEffect(() => {
        if (jsonApiResponse && onRessourceResponse){
            onRessourceResponse(jsonApiResponse);
            setIsInitialized(true);
        }
    }, [onRessourceResponse, jsonApiResponse]);

    useEffect(() => {
        if (!isRessourceLoading && getRessourceResponse){
            setLoading(false);
        }
    }, [isRessourceLoading, getRessourceResponse]);
    
    return (
        <PageContainer
            header={
                {
                    title: intl.formatMessage(
                        { id: 'component.ressourceDetails.pageContainer.title' },
                        { 
                            ressourceType: ressource?.type, 
                            label: ressource?.attributes?.stringRepresentation 
                        },
                      ),
                    
                }

            }
            loading={loading}
        > 
            {children}
        </PageContainer>
    );

};


export default RessourceDetails;
