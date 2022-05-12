import OgcServiceDetails from "@/components/RessourceDetails/OgcServiceDetails";
import type { JsonApiDocument, JsonApiPrimaryData } from "@/utils/jsonapi";
import { getIncludesByType } from "@/utils/jsonapi";
import type { DefaultOptionType } from 'antd/lib/select';
import type { ParamsArray } from "openapi-client-axios";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";
import { useIntl } from 'umi';


interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    isLeaf: boolean
}

const transformTreeData = (wms: JsonApiDocument): Node[] => {
    return getIncludesByType(wms, 'FeatureType').map((node) => {
        return {
            key: node.id, 
            title: node.attributes.stringRepresentation, 
            raw: node,
            isLeaf: true,
        }
    });
    
};

const WfsDetails = (): ReactElement => {
    /**
     * page hooks
     */
    const intl = useIntl();
    //const [ treeData, setTreeData ] = useState<Node[]>();
    const [ searchOptions, setSearchOptions ] = useState<DefaultOptionType[]>([]);

    const [ reFetchRessource, setRefetchRessource ] = useState<boolean>(false);


    /**
     * derived constants
     */
     const getWebFeatureServiceParams: ParamsArray = [
        {
            in: 'query',
            name: 'include',
            value: 'featuretypes',
        },
        {
            in: 'query',
            name: 'fields[FeatureType]',
            value: 'string_representation,is_active,dataset_metadata'
        }
    ];

    const onRessourceResponse = useCallback((ressource: JsonApiDocument) => {        
        setRefetchRessource(false);
        setTreeData(transformTreeData(ressource));

        const newSearchOptions: DefaultOptionType[] = getIncludesByType(ressource, 'FeatureType').map((node: JsonApiPrimaryData) => {
            return {
                value: node.id,
                label: node.attributes.stringRepresentation
            }
        })
        setSearchOptions(newSearchOptions);
    }, []);
    
    return (
        <OgcServiceDetails
            resourceType='WebFeatureService'
            additionalGetRessourceParams={getWebFeatureServiceParams}
            onRessourceResponse={onRessourceResponse}
            rebuild={reFetchRessource}
         />
    );

};


export default WfsDetails;
