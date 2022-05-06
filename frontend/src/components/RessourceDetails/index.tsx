import type { JsonApiDocument, JsonApiPrimaryData } from "@/utils/jsonapi";
import { PageContainer } from "@ant-design/pro-layout";
import type { AxiosError, ParamsArray } from "openapi-client-axios";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";
import { useOperationMethod } from "react-openapi-client/useOperationMethod";
import { history, useIntl, useParams } from 'umi';

interface RessourceDetailsProps {
    children?: ReactNode | undefined
    onRessourceResponse?: (ressource: JsonApiDocument) => void;
    resourceType: string;
    additionalGetRessourceParams?: ParamsArray;
    callGetRessource?: boolean;
    //callGetRessource?: (call: boolean) => void;
    //pageContainerExtra?
}

const RessourceDetails = ({
    children = undefined,
    onRessourceResponse = undefined,
    resourceType,
    additionalGetRessourceParams = [],
    callGetRessource = false,
}: RessourceDetailsProps): ReactElement => {
    /**
     * page hooks
     */
    const intl = useIntl();
    const { id } = useParams<{ id: string }>();
    const [ loading, setLoading ] = useState(true);
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

    const getRessourceParams: ParamsArray = [
        ...additionalGetRessourceParams,
        {
            in: 'path',
            name: 'id',
            value: String(id),
        }
    ]

    /**
     * @description hook to receive the resource on initial
     */
    useEffect(() => {
        console.log('callGetRessource',callGetRessource);
        if (!isRessourceLoading || !isRessourceLoading && callGetRessource){
            getRessource(getRessourceParams);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [callGetRessource]);


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
            console.log('jsonApiResponse', jsonApiResponse);
            onRessourceResponse(jsonApiResponse);
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
